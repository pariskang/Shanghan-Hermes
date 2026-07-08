"""OmniSearch — 全景多路檢索（字詞 · 本體擴展 · 圖譜 · 現代映射 · 全庫旁證）.

從「查詞」升級為「查知識鏈」，同時守住兩條工程底線：

  誠實：每條命中標注 evidence_type——直接原文 / 本體擴展 / 圖譜關聯 /
        現代映射 / 文獻旁證——擴展召回絕不冒充原文精確命中；現代疾病
        映射帶等級（A-D）與固定免責，不作病名等同。
  高效：全部通道走內存索引。傷寒論 BM25 單查 <1ms；同義擴展 ≤8 詞
        （每詞一次 BM25）；圖譜鄰接為預載關係表；笈成全庫全文通道
        （可選）走字符倒排剪枝，典型 30-250ms——默認配置整體目標
        <100ms，含全庫通道 <600ms。latency_ms 隨結果返回，可回歸監控。

重排為確定性加權（無不可復現的學習排序）：
  score = channel_weight × bm25_norm + 直接命中加成 + 多通道匯聚加成
"""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional

from .. import lexicon, ontology, phenotype_map
from ..textutil import normalize_query

# 通道權重（方案 §9 的固定權重思想，但通道內用真實 BM25 分而非拍腦袋常數）
CHANNEL_WEIGHT = {
    "直接原文": 1.0,
    "本體擴展": 0.65,
    "語義向量": 0.6,
    "現代映射": 0.55,
    "圖譜關聯": 0.45,
    "文獻旁證": 0.4,
}

RE_CLAUSE_REF = re.compile(r"第?\s*(\d{1,3})\s*條|SHL_SONGBEN_(?:AUX_)?\d{4}")


class OmniSearch:
    def __init__(self, clause_rag=None, registry=None):
        if clause_rag is None:
            from .clause_rag import ClauseRAG
            clause_rag = ClauseRAG.load()
        self.rag = clause_rag
        self._registry = registry            # optional, for graph relations
        self._lib = None                     # cached Library (char index 常駐)

    def _library(self):
        if self._lib is None:
            from ..corpus import library
            if library.ensure_available(verbose=False):
                self._lib = library.Library()
                self._lib._load_charindex()   # 預載字符倒排，後續查詢常駐內存
        return self._lib

    # ------------------------------------------------------------------
    def understand(self, query: str) -> Dict:
        """查詢理解：意圖 + 概念抽取（原文/方/藥/病證/現代疾病）。"""
        q = normalize_query(query)
        from ..extract.entities import EntityExtractor
        found = EntityExtractor().extract(q)
        formulas = [n for n in sorted(lexicon.FORMULA_SEEDS, key=len,
                                      reverse=True) if n in q][:3]
        modern = phenotype_map.detect_modern(q)
        if RE_CLAUSE_REF.search(query):
            intent = "原文考據"
        elif modern and not formulas:
            intent = "現代疾病映射"
        elif formulas:
            intent = "方劑檢索"
        elif found.symptoms or found.pulse or found.disease_patterns:
            intent = "病證檢索"
        else:
            intent = "一般檢索"
        concepts = list(dict.fromkeys(
            found.symptoms + found.disease_patterns + found.pulse
            + ontology.detect_terms(q)))[:6]
        return {"intent": intent, "modern": modern, "formulas": formulas,
                "concepts": concepts, "normalized": q}

    # ------------------------------------------------------------------
    def search(self, query: str, top_k: int = 8,
               include_library: bool = False,
               channels: Optional[List[str]] = None,
               library_budget_ms: int = 450) -> Dict:
        t0 = time.perf_counter()
        u = self.understand(query)
        enabled = set(channels or CHANNEL_WEIGHT)
        pool: Dict[str, Dict] = {}          # clause_id → merged hit
        trace: List[Dict] = []

        def add(hit: Dict, channel: str, term: str, raw_score: float):
            cid = hit.get("clause_id")
            if not cid:
                return
            score = CHANNEL_WEIGHT[channel] * raw_score
            e = pool.get(cid)
            if e is None:
                pool[cid] = {"clause_id": cid,
                             "text": hit.get("text", "")[:120],
                             "six_channel": hit.get("six_channel", ""),
                             "channels": [channel],
                             "matched_terms": [term],
                             "evidence_type": channel,
                             "score": score}
            else:
                if channel not in e["channels"]:
                    e["channels"].append(channel)
                    e["score"] += 0.15 * raw_score     # 多通道匯聚加成
                if term not in e["matched_terms"]:
                    e["matched_terms"].append(term)
                if CHANNEL_WEIGHT[channel] > CHANNEL_WEIGHT[e["evidence_type"]]:
                    e["evidence_type"] = channel       # 取最強證據類型
                e["score"] = max(e["score"], score)

        # 1 — 直接原文（BM25 + 結構化） ————————————————————————
        if "直接原文" in enabled:
            n = 0
            for h in self.rag.search(u["normalized"], top_k=top_k):
                add(h, "直接原文", u["normalized"][:16], self._norm(h))
                n += 1
            trace.append({"channel": "直接原文", "queries": 1, "hits": n})

        # 2 — 本體擴展（同義組 + 方名/藥名歸一） ——————————————————
        expanded: List[str] = []
        if "本體擴展" in enabled:
            expanded = [t for t in ontology.expand_terms(
                u["concepts"] or [u["normalized"]])
                if t != u["normalized"]][:8]
            n = 0
            for term in expanded:
                for h in self.rag.search(term, top_k=3):
                    add(h, "本體擴展", term, self._norm(h))
                    n += 1
            trace.append({"channel": "本體擴展", "queries": len(expanded),
                          "terms": expanded, "hits": n})

        # 2b — 語義向量（embeddings 增益 / char-tfidf 確定性兜底） ————
        if "語義向量" in enabled:
            from .vector_channel import get_vector_channel
            vc = get_vector_channel()
            vout = vc.search(u["normalized"], top_k=min(top_k, 6))
            for h in vout.get("hits", []):
                if h["relevance"] >= 0.35:
                    add(h, "語義向量", f"cos:{h['relevance']}", h["relevance"])
            trace.append({"channel": "語義向量",
                          "backend": vout.get("backend"),
                          "hits": len(vout.get("hits", []))})

        # 3 — 現代映射（表型→病機→古籍詞） ————————————————————
        mapping = None
        if "現代映射" in enabled and u["modern"]:
            mapping = phenotype_map.map_modern(u["modern"])
            n = 0
            for term in mapping["classical_terms"][:6]:
                for h in self.rag.search(term, top_k=3):
                    add(h, "現代映射", term, self._norm(h))
                    n += 1
            trace.append({"channel": "現代映射", "modern": u["modern"],
                          "grade": mapping["grade"], "hits": n})

        # 4 — 圖譜關聯（top 命中的關係鄰接） ———————————————————
        if "圖譜關聯" in enabled and pool:
            top_now = sorted(pool.values(), key=lambda x: -x["score"])[:3]
            n = 0
            for e in top_now:
                for r in self.rag.related(e["clause_id"], limit=3):
                    c = self.rag.get_clause(r.get("clause_id", ""))
                    add({"clause_id": r.get("clause_id"),
                         "text": (c.clean_text if c else ""),
                         "six_channel": (c.six_channel if c else "")},
                        "圖譜關聯", r.get("relation_type", "關聯"), 0.8)
                    n += 1
            trace.append({"channel": "圖譜關聯", "hits": n})

        # 5 — 文獻旁證（笈成全庫，可選；字符倒排剪枝） ———————————
        library_hits: List[Dict] = []
        if include_library and "文獻旁證" in enabled:
            lib = self._library()
            if lib is not None:
                probe = ([u["modern"]] if u["modern"] else [])
                probe += (mapping["classical_terms"][:2] if mapping else [])
                probe += (u["concepts"][:2] if not mapping else [])
                probe = list(dict.fromkeys(
                    t for t in probe if t and len(t) >= 2))[:4] \
                    or [u["normalized"][:8]]
                # 段落級多詞檢索（條文粒度，pid 可回源）：一次調用同時
                # 檢索全部探針詞，同段共現優先；硬時間預算內完成，
                # 超限顯式 truncated
                out = lib.search_passages(probe, limit=8, per_book=2,
                                          max_scan=24,
                                          budget_ms=library_budget_ms)
                for h in out.get("hits", []):
                    library_hits.append(
                        {"book": h["title"], "section": h["section"],
                         "pid": h["pid"],
                         "excerpt": h["excerpt"][:90],
                         "matched_term": "、".join(h["matched_terms"]),
                         "evidence_type": "文獻旁證",
                         "layer": "旁證（非經文層，不進入證據閘門）"})
                trace.append({"channel": "文獻旁證", "terms": probe,
                              "granularity": "段落級",
                              "hits": len(library_hits),
                              "budget_ms": library_budget_ms,
                              "truncated": out.get("truncated", False)})
            else:
                trace.append({"channel": "文獻旁證",
                              "hits": 0, "note": "全庫未下載（library fetch）"})

        hits = sorted(pool.values(), key=lambda x: (-x["score"], x["clause_id"]))
        for h in hits:
            h["score"] = round(h["score"], 3)
        out = {
            "query": query,
            "understanding": u,
            "expanded_terms": expanded,
            "modern_mapping": mapping,          # 含 grade + disclaimer
            "hits": hits[:top_k],
            "n_pool": len(pool),
            "library_hits": library_hits[:8],
            "channel_trace": trace,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "note": ("每條命中標 evidence_type；本體擴展/現代映射為召回擴展，"
                     "非原文精確命中；現代映射不作病名等同。"),
        }
        return out

    @staticmethod
    def _norm(hit: Dict) -> float:
        """BM25 分歸一到 0-1（傷寒論語料的典型分值域）。"""
        s = float(hit.get("score", 1.0) or 1.0)
        return max(0.1, min(1.0, s / 12.0))


_OMNI: Optional[OmniSearch] = None


def get_omni() -> OmniSearch:
    global _OMNI
    if _OMNI is None:
        _OMNI = OmniSearch()
    return _OMNI
