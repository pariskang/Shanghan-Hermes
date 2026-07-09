"""深度溯源引擎（provenance）——從「查出處」升級為「追蹤知識生命史」.

普通古籍溯源只回答「這句話出自哪本書」；本引擎回答一個知識單元
（條文 / 方劑 / 概念 / 方證觀點）的完整生命史：

    原始條文 → 版本異文 → 注家解釋 → 後世方論/醫案 → 現代疾病映射
             → 現代機制橋接 → 科研熱點

工程取捨（合理採納 · 不合理改進）：

1. **不建 9 個新智能體**：溯源不是九條獨立流水線，而是把既有工具
   （get_clause / variants / divergence_atlas / relations / correspondence /
   library）編排為一條知識鏈——一個 ``ProvenanceTracer`` 復用它們，能力
   相同而無編排臃腫。

2. **現代文獻計量走可插拔連接器，離線誠實降級**：Crossref / OpenAlex /
   Semantic Scholar 等需外網，硬接會（a）破壞離線確定性與可測性，
   （b）受網絡策略約束，（c）若無數據即編造論文/DOI——恰是原方案自己
   列為失敗指標的「幻覺」。因此定義 ``ScholarConnector`` 協議 +
   ``NullScholarConnector``（離線默認）：現代計量層只輸出**能離線推導的
   古籍→現代橋接**（熱點/機制候選來自表型映射），而 core_papers/authors
   一律標「需接入外部引文源」，絕不虛構。與既有 litellm/向量增益層同構。

證據分層貫穿全鏈：A 原文直述 / B 版本異文 / C 注家解釋 / D 後世歸納 /
D現代映射（候選，不作病名等同）/ deferred 現代計量。輸出時明確區分，
決不把後世發揮或現代機制冒充原文。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Protocol

from .. import lexicon
from ..textutil import cjk_chars, normalize_query, similarity

# 明引標記語：書名之後接「曰/云/載/謂/言」即為顯性引用
RE_EXPLICIT_MARK = re.compile(r"[《〈][^》〉]{1,12}[》〉]\s*[曰云載謂言：:]")
RE_BOOK_TITLE = re.compile(r"[《〈]([^》〉]{1,14})[》〉]")

# 概念級知識單元（跨書命題）→ 傷寒論可錨定的核心詞 + 表型映射入口。
# 傷寒論原典未直述者（如「腎主骨」源出《內經》）誠實標源頭 deferred，
# 仍給後世反響（醫案全庫）與現代映射，不硬湊原典出處。
CONCEPT_ALIASES = {
    "營衛不和": ["營衛", "榮衛", "汗自出", "衛強榮弱"],
    "腎主骨": ["腎主骨", "骨痿", "骨痹", "髓"],
    "肝主筋": ["肝主筋", "筋"],
    "太陽中風": ["太陽中風", "中風", "桂枝"],
}


class ScholarConnector(Protocol):
    """現代學術元數據/引文連接器協議（Crossref/OpenAlex/Semantic Scholar/
    OpenCitations 的統一抽象）。實現者返回真實論文/引文；未接入時由
    ``NullScholarConnector`` 誠實降級——本系統離線默認絕不虛構。"""

    name: str

    def works(self, query: str, limit: int = 10) -> List[Dict]:
        ...


class NullScholarConnector:
    """離線默認連接器：不虛構任何論文。返回空集並標 deferred，讓計量層
    誠實聲明「需接入外部引文源」，而非編造 core_papers/DOI。"""

    name = "null"

    def works(self, query: str, limit: int = 10) -> List[Dict]:
        return []


# ── 引文模式（§6：明引/暗引/節引/改寫/轉引/誤引）——————————————
def _ngram_overlap(a: str, b: str, n: int = 3) -> float:
    ca, cb = cjk_chars(a), cjk_chars(b)
    if len(ca) < n or len(cb) < n:
        return 0.0
    ga = {"".join(ca[i:i + n]) for i in range(len(ca) - n + 1)}
    gb = {"".join(cb[i:i + n]) for i in range(len(cb) - n + 1)}
    return len(ga & gb) / max(1, len(ga))


def _longest_run(target: str, source: str) -> int:
    """最長連續片段：target 的漢字子串在 source 中連續出現的最大長度。
    只取 CJK 字符——對標點/空白/字形變體魯棒（節引/暗引判別的核心）。"""
    from ..textutil import fold_variants
    t = fold_variants("".join(cjk_chars(target)))
    s = fold_variants("".join(cjk_chars(source)))
    best = 0
    for i in range(len(t)):
        j = i + best + 1
        while j <= len(t) and t[i:j] in s:
            best = j - i
            j += 1
    return best


def classify_citation(source_text: str, target_text: str,
                      via_later_work: bool = False,
                      claimed_ref: Optional[str] = None,
                      actual_ref: Optional[str] = None) -> Dict[str, Any]:
    """判定 source_text（後世/現代文本）對 target_text（早期原典條文）的
    引用模式。返回 {pattern, confidence, signals}。

    明引 explicit：含「《書名》曰/云」標記且文字高度重合
    暗引 implicit：文字高度重合但無標記（直接化用）
    節引 partial：只重合原文一個片段（高 n-gram、低整體相似）
    改寫 paraphrase：語義相近但逐字重合低（意譯）
    轉引 relay：經後世注本/教材中轉（via_later_work）
    誤引 mis-citation：claimed_ref 與 actual_ref 不符
    """
    tcjk = "".join(cjk_chars(target_text))
    run = _longest_run(target_text, source_text)
    whole = bool(tcjk) and run >= len(tcjk)      # 標點魯棒的整句containment
    ngram = _ngram_overlap(target_text, source_text)
    sim = similarity(source_text, target_text)
    has_mark = bool(RE_EXPLICIT_MARK.search(source_text))
    signals = {"whole": whole, "longest_run": run, "ngram3": round(ngram, 3),
               "similarity": round(sim, 3), "explicit_mark": has_mark}

    if claimed_ref and actual_ref and claimed_ref != actual_ref:
        return {"pattern": "誤引", "confidence": 0.6, "signals": signals,
                "note": f"標稱來源 {claimed_ref} 與最佳匹配 {actual_ref} 不符"}
    if via_later_work:
        return {"pattern": "轉引", "confidence": 0.55, "signals": signals,
                "note": "經後世注本/醫案/教材中轉，非直引原典"}
    if whole and has_mark:
        return {"pattern": "明引", "confidence": 0.9, "signals": signals}
    if whole:
        return {"pattern": "暗引", "confidence": 0.78, "signals": signals}
    if run >= 5:            # 只覆蓋原文一個連續片段 → 節引
        return {"pattern": "節引", "confidence": 0.7, "signals": signals}
    if sim >= 0.35 or ngram >= 0.3:
        return {"pattern": "改寫", "confidence": 0.55, "signals": signals}
    return {"pattern": "無明顯引用", "confidence": 0.2, "signals": signals}


# ── 影響力指標打分（§13）——確定性，逐項附依據 ————————————————
def _band(v: float) -> str:
    return "高" if v >= 0.66 else ("中" if v >= 0.33 else "低")


class ProvenanceTracer:
    """知識生命史追溯器。復用註冊表工具，不新建智能體。"""

    def __init__(self, registry, connector: Optional[ScholarConnector] = None):
        self.reg = registry
        self.connector = connector or NullScholarConnector()

    # ------------------------------------------------------------------
    def _clause_text(self, clause_id: str) -> str:
        cl = self.reg.art.clause_store().get(clause_id)
        return cl.clean_text if cl is not None else ""

    def _concept_id(self, label: str) -> str:
        # 穩定 ConceptID：規範化 + 折疊，供跨書追蹤（§5）
        norm = normalize_query(label)
        return "CONCEPT_" + re.sub(r"[^0-9A-Za-z一-鿿]", "", norm)[:24]

    # ------------------------------------------------------------------
    def trace(self, ref: Optional[str] = None, formula: Optional[str] = None,
              concept: Optional[str] = None,
              text: Optional[str] = None) -> Dict[str, Any]:
        if ref:
            return self._trace_clause(ref)
        if formula:
            return self._trace_formula(formula)
        if concept or text:
            return self._trace_concept(concept or text, raw_text=text)
        return {"tool": "shanghan_provenance",
                "error": "請提供 ref（條文號）/ formula（方名）/ concept（概念或方證觀點）/ text（待溯源文本）之一"}

    # ── 條文級：原文溯源鏈（原文→異文→注釋→後世反響）——————————
    def _trace_clause(self, ref: str) -> Dict[str, Any]:
        var = self.reg.call("shanghan_variants", {"ref": ref})
        if var.get("error"):
            return {"tool": "shanghan_provenance", "error": var["error"]}
        clause_id = var["clause_id"]
        base_text = var["base_text"]
        m = re.search(r"(\d{4})$", clause_id)
        clause_no = int(m.group(1)) if m else None
        div = self.reg.call("shanghan_divergence_atlas",
                            {"clause": clause_id[-4:]})
        rel = self.reg.call("shanghan_relations", {"ref": ref})

        # 源頭段：傷寒論宋本為底本（A 層直述）
        source_trace = {
            "earliest_sources": [{
                "work": "傷寒論（宋本·趙開美本）", "edition_id": "SHL_SONGBEN",
                "clause_id": clause_id, "text": base_text,
                "evidence_type": "classical_direct", "layer": "A",
                "confidence": 0.95}],
            "variant_notes": self._variant_note(var),
        }

        # 文本鏈：A 原文 → B 異文 → C 注家 → 後世反響
        lineage: List[Dict] = [
            {"stage": "原始條文", "layer": "A", "source": clause_id,
             "detail": base_text}]
        for v in var.get("variants", []):
            lineage.append({
                "stage": "版本異文", "layer": "B", "source": v["book"],
                "similarity": v["similarity"],
                "detail": "、".join(v.get("notable_differences", [])[:2])
                          or f"與宋本相似度 {v['similarity']}"})
        cl_div = self._clause_divergence(div, clause_id)
        if cl_div:
            for name, terms in list(
                    cl_div.get("distinctive_terms", {}).items())[:3]:
                lineage.append({
                    "stage": "注家解釋", "layer": "C", "source": name,
                    "detail": f"特徵術語：{'、'.join(terms)}"})

        # 後世反響：全庫醫案/方書是否化用本條核心（轉引/暗引偵測）
        reception = self._later_reception(base_text)

        # 引文邊（§10.2 typed edges）：注家/後世對本條的引用關係
        edges = self._clause_edges(clause_id, base_text, cl_div, reception)

        idx = self._clause_influence(var, cl_div, rel, reception)
        return {
            "tool": "shanghan_provenance",
            "target": {"kind": "clause", "id": clause_id,
                       "ids": {"WorkID": "SHL", "EditionID": "SHL_SONGBEN",
                               "ClauseID": clause_id},
                       "label": f"第{clause_no}條" if clause_no else clause_id},
            "source_trace": source_trace,
            "text_lineage": lineage,
            "citation_edges": edges,
            "later_reception": reception,
            "concept_evolution": self._concept_evolution_from_text(base_text),
            "bibliometric_trace": self._bibliometric(base_text),
            "influence_index": idx,
            "evidence_warning": self._warning(),
            "boundary": ("溯源鏈跨 A/B/C/D 層並逐段標注；現代計量層為 deferred "
                         "augmentation（需接入外部引文源，離線不虛構論文）；"
                         "用於知識演化研究，不構成臨床處方依據。"),
            "evidence_level": "溯源鏈 A/B/C/D + 現代計量 deferred",
            "confidence": 0.8,
        }

    # ── 方劑級：方劑源流鏈（原方→類方→加減→後世方論）——————————
    def _trace_formula(self, formula: str) -> Dict[str, Any]:
        from .correspondence import CorrespondenceEngine
        rules = [f for f in self.reg.art.formula_rules if f.formula == formula]
        if not rules:
            cand = [f.formula for f in self.reg.art.formula_rules
                    if formula and (formula in f.formula or f.formula in formula)][:5]
            return {"tool": "shanghan_provenance",
                    "error": f"方名「{formula}」未見於方證規則庫",
                    "candidates": cand}
        fr = rules[0]
        grade = CorrespondenceEngine(self.reg).relation_grade(formula)
        supp = list(fr.supporting_clauses)[:8]
        earliest = supp[0] if supp else None
        lineage: List[Dict] = [{
            "stage": "原方出處", "layer": "A", "source": earliest or formula,
            "detail": (self._clause_text(earliest)[:60] if earliest else
                       "見於方證規則庫")}]
        for mr in (fr.modification_relations or [])[:6]:
            added = mr.get("added_herbs", ""); removed = mr.get("removed_herbs", "")
            chg = "；".join(x for x in (f"加 {added}" if added else "",
                                        f"去 {removed}" if removed else "") if x)
            lineage.append({
                "stage": "加減/類方", "layer": "D", "source": mr["modified_formula"],
                "detail": f"{mr.get('relation', '類方')}{('：' + chg) if chg else ''}"})
        reception = self._later_reception(formula, is_formula=True)

        idx = self._formula_influence(fr, grade, reception)
        return {
            "tool": "shanghan_provenance",
            "target": {"kind": "formula", "id": formula,
                       "ids": {"WorkID": "SHL",
                               "FormulaID": fr.formula_pattern_rule_id,
                               "family": fr.formula_family},
                       "label": formula},
            "source_trace": {
                "earliest_sources": [{
                    "work": "傷寒論（宋本）", "edition_id": "SHL_SONGBEN",
                    "clause_id": earliest, "evidence_type": "classical_direct",
                    "layer": "A", "confidence": 0.9,
                    "text": self._clause_text(earliest)[:50] if earliest else ""}],
                "relation_grade": {"grade": grade["grade"],
                                   "relation": grade["relation"],
                                   "basis": grade["basis"]},
                "variant_notes": f"方族「{fr.formula_family}」共 {len(supp)} 條方證條文支撐"},
            "text_lineage": lineage,
            "citation_edges": self._formula_edges(fr, reception),
            "later_reception": reception,
            "concept_evolution": self._concept_evolution_from_text(
                "、".join(fr.core_symptoms[:6])),
            "bibliometric_trace": self._bibliometric(formula),
            "influence_index": idx,
            "evidence_warning": self._warning(),
            "boundary": ("方劑源流鏈以宋本為底本；加減/類方為 D 層跨條歸納；"
                         "現代計量層 deferred。不構成處方建議。"),
            "evidence_level": "源流鏈 A/D + 現代計量 deferred",
            "confidence": 0.78,
        }

    # ── 概念/方證觀點級：知識演化鏈（原典→後世發揮→現代映射）————
    def _trace_concept(self, concept: str,
                       raw_text: Optional[str] = None) -> Dict[str, Any]:
        concept = concept.strip()
        aliases = CONCEPT_ALIASES.get(concept, [concept])
        # 原典錨定：概念詞是否直述於傷寒論原文
        hits = self.reg.call("shanghan_search",
                             {"query": " ".join(aliases[:3]), "top_k": 6})
        clause_hits = hits.get("hits", hits.get("results", []))
        direct = [h for h in clause_hits
                  if any(a in h.get("text", "") for a in aliases)][:4]

        if direct:
            source_trace = {
                "earliest_sources": [{
                    "work": "傷寒論（宋本）", "edition_id": "SHL_SONGBEN",
                    "clause_id": h.get("clause_id"),
                    "text": h.get("text", "")[:60],
                    "evidence_type": "classical_direct", "layer": "A",
                    "confidence": 0.8} for h in direct],
                "variant_notes": "概念詞直述於傷寒論原文（A 層）"}
            src_note = "本系統原典庫（傷寒論）直接錨定"
        else:
            # 傷寒論未直述（如「腎主骨」源出《內經》）——誠實 deferred，
            # 決不硬湊原典出處
            source_trace = {
                "earliest_sources": [{
                    "work": "《內經》等更早原典（本系統以傷寒論為主庫，未收）",
                    "edition_id": None, "clause_id": None,
                    "evidence_type": "deferred_earlier_classic", "layer": "deferred",
                    "confidence": 0.0,
                    "note": "該命題最早源頭需《內經》等原典庫，本庫未直接收錄——"
                            "不虛構出處，僅給傷寒論相關語境與後世反響"}],
                "variant_notes": "傷寒論原文未直述本命題；下列為相關語境與後世反響"}
            src_note = "傷寒論原典未直述（源頭 deferred）"

        reception = self._later_reception(aliases[0])
        evolution = self._concept_evolution(concept, aliases, direct)
        idx = self._concept_influence(direct, reception, evolution)
        return {
            "tool": "shanghan_provenance",
            "target": {"kind": "concept", "id": self._concept_id(concept),
                       "ids": {"ConceptID": self._concept_id(concept),
                               "ClaimID": "CLAIM_" + self._concept_id(concept)[8:]},
                       "label": concept},
            "source_note": src_note,
            "source_trace": source_trace,
            "text_lineage": [
                {"stage": "傷寒論相關語境", "layer": "A" if direct else "—",
                 "source": h.get("clause_id"), "detail": h.get("text", "")[:60]}
                for h in direct] or [
                {"stage": "傷寒論相關語境", "layer": "—", "source": None,
                 "detail": "原文未直述"}],
            "citation_edges": self._concept_edges(aliases[0], reception),
            "later_reception": reception,
            "concept_evolution": evolution,
            "bibliometric_trace": self._bibliometric(concept),
            "influence_index": idx,
            "evidence_warning": self._warning(),
            "boundary": ("概念溯源區分原典直述（A）、後世發揮（D）與現代映射"
                         "（候選，不作病名等同）；現代計量層 deferred。"),
            "evidence_level": "演化鏈 A/D/現代映射 + 計量 deferred",
            "confidence": 0.7,
        }

    # ── 後世反響：全庫醫案/方書是否化用（轉引/暗引）——————————
    def _later_reception(self, needle: str,
                         is_formula: bool = False) -> List[Dict]:
        lib = self.reg.call("shanghan_library",
                            {"query": needle[:12], "top_k": 6})
        if not lib.get("available") or lib.get("error"):
            return []
        out: List[Dict] = []
        for h in lib.get("text_hits", [])[:6]:
            excerpt = h.get("excerpt", "")
            cite = classify_citation(excerpt, needle, via_later_work=True)
            out.append({
                "book": h.get("title") or h.get("book_id"),
                "category": h.get("category", ""),
                "section": h.get("section", "")[:16],
                "excerpt": excerpt[:80],
                "citation_pattern": cite["pattern"],
                "citation_confidence": cite["confidence"],
                "layer": "旁證（非經文層）"})
        return out

    # ── 概念演化：經典理論 → 後世發揮 → 現代映射（§12）——————————
    def _concept_evolution(self, concept: str, aliases: List[str],
                           direct: List[Dict]) -> List[Dict]:
        stages: List[Dict] = []
        stages.append({
            "stage": "經典理論", "concept": concept,
            "role": "理論源頭" if direct else "相關語境",
            "layer": "A" if direct else "—",
            "evidence": [h.get("clause_id") for h in direct] or None})
        # 後世發揮：全庫醫案/方書中的擴展表述
        recep = self._later_reception(aliases[0])
        if recep:
            stages.append({
                "stage": "後世發揮", "concept": f"{concept}（後世化用/擴展）",
                "role": "病機/應用擴展", "layer": "D",
                "evidence": [r["book"] for r in recep[:3]]})
        # 現代映射：表型映射鏈
        mm = self._modern_mapping(concept, aliases)
        if mm:
            stages.append({
                "stage": "現代轉化", "concept": mm["modern"],
                "role": "現代疾病映射（候選，不作病名等同）",
                "layer": "D 現代映射", "grade": mm.get("grade"),
                "evidence": mm.get("classical_terms", [])[:4]})
        return stages

    def _concept_evolution_from_text(self, text: str) -> List[Dict]:
        # 從條文/方劑症狀文本推演化：只在能映射到現代疾病時追加現代段
        stages = [{"stage": "經典理論", "concept": text[:40], "role": "原文語境",
                   "layer": "A", "evidence": None}]
        for concept, aliases in CONCEPT_ALIASES.items():
            if any(a in text for a in aliases):
                mm = self._modern_mapping(concept, aliases)
                if mm:
                    stages.append({
                        "stage": "現代轉化", "concept": mm["modern"],
                        "role": "現代疾病映射（候選）", "layer": "D 現代映射",
                        "grade": mm.get("grade"),
                        "evidence": mm.get("classical_terms", [])[:4]})
                    break
        return stages

    def _modern_mapping(self, concept: str,
                        aliases: List[str]) -> Optional[Dict]:
        from .. import phenotype_map as pm
        for term in [concept] + aliases:
            hit = pm.map_modern(term)
            if hit:
                return hit
        # 反向：古籍病名 → 現代（detect_modern 走現代名；此處嘗試經 correspondence）
        out = self.reg.call("shanghan_correspondence", {"modern": concept})
        return out.get("modern_mapping")

    # ── 現代計量層（誠實 deferred；不虛構）——————————————————
    def _bibliometric(self, topic: str) -> Dict[str, Any]:
        works = self.connector.works(topic)
        # 離線可推導的橋接：表型映射給出的現代熱點方向與機制候選
        hot_topics: List[str] = []
        mechanism_bridge: List[str] = []
        for concept, aliases in CONCEPT_ALIASES.items():
            if concept in topic or any(a in topic for a in aliases):
                mm = self._modern_mapping(concept, aliases)
                if mm:
                    hot_topics = mm.get("methods_hint", [])[:4]
                    mechanism_bridge = mm.get("phenotypes", [])[:4]
                break
        if works:
            return {"connector": self.connector.name, "status": "connected",
                    "core_papers": works[:10],
                    "hot_topics": hot_topics,
                    "modern_mechanism_bridge": mechanism_bridge,
                    "citation_function": "theoretical_basis"}
        return {
            "connector": self.connector.name,
            "status": ("deferred：現代計量需接入外部引文源"
                       "（Crossref/OpenAlex/Semantic Scholar/OpenCitations）；"
                       "離線不虛構論文/DOI/作者"),
            "core_papers": [], "core_authors": [], "core_institutions": [],
            "hot_topics": hot_topics,
            "modern_mechanism_bridge": mechanism_bridge,
            "citation_function": "theoretical_basis",
            "note": ("機制候選僅為表型/病機層橋接，不與中醫概念機械等同；"
                     "接入連接器後方可產出真實 core_papers 與引文網絡。")}

    # ── 引文邊 typed（§10.2）—————————————————————————————
    def _clause_edges(self, clause_id: str, base_text: str,
                      cl_div: Optional[Dict], reception: List[Dict]) -> List[Dict]:
        edges: List[Dict] = []
        eid = 0
        for name in (cl_div or {}).get("commentators", [])[:5]:
            eid += 1
            edges.append({
                "edge_id": f"CITE_{clause_id}_{eid:03d}",
                "source": name, "target": clause_id,
                "citation_type": "理論引用", "citation_function": "注釋闡發",
                "citation_attitude": "supportive",
                "evidence_strength": 0.7,
                "context": "注家逐條詮釋", "layer": "C"})
        for r in reception[:4]:
            eid += 1
            edges.append({
                "edge_id": f"CITE_{clause_id}_{eid:03d}",
                "source": r["book"], "target": clause_id,
                "citation_type": "病證映射" if r["category"] == "醫案" else "理論引用",
                "citation_function": "臨床應用" if r["category"] == "醫案" else "理論借用",
                "citation_attitude": "supportive",
                "evidence_strength": r["citation_confidence"],
                "context": f"{r['category']}·{r['citation_pattern']}",
                "layer": "旁證"})
        return edges

    def _formula_edges(self, fr, reception: List[Dict]) -> List[Dict]:
        edges: List[Dict] = []
        for i, mr in enumerate((fr.modification_relations or [])[:6], 1):
            edges.append({
                "edge_id": f"CITE_{fr.formula_pattern_rule_id}_{i:03d}",
                "source": mr["modified_formula"], "target": fr.formula,
                "citation_type": "方劑引用", "citation_function": "加減化裁",
                "citation_attitude": "extension",
                "evidence_strength": 0.75,
                "context": mr.get("relation", "類方"), "layer": "D"})
        for j, r in enumerate(reception[:4], len(edges) + 1):
            edges.append({
                "edge_id": f"CITE_{fr.formula_pattern_rule_id}_{j:03d}",
                "source": r["book"], "target": fr.formula,
                "citation_type": "方劑引用", "citation_function": "臨床應用",
                "citation_attitude": "supportive",
                "evidence_strength": r["citation_confidence"],
                "context": f"{r['category']}·{r['citation_pattern']}",
                "layer": "旁證"})
        return edges

    def _concept_edges(self, needle: str, reception: List[Dict]) -> List[Dict]:
        return [{
            "edge_id": f"CITE_CONCEPT_{i:03d}",
            "source": r["book"], "target": needle,
            "citation_type": "理論引用", "citation_function": "理論借用",
            "citation_attitude": "supportive",
            "evidence_strength": r["citation_confidence"],
            "context": f"{r['category']}·{r['citation_pattern']}（轉引）",
            "layer": "旁證"} for i, r in enumerate(reception[:5], 1)]

    # ── 影響力指標（§13）—————————————————————————————
    def _clause_influence(self, var: Dict, cl_div: Optional[Dict],
                          rel: Dict, reception: List[Dict]) -> Dict:
        n_comm = (cl_div or {}).get("n_commentators", 0)
        dispute = (cl_div or {}).get("term_divergence", 0.0) or 0.0
        n_var = var.get("n_variants", 0)
        var_sim = ([v["similarity"] for v in var.get("variants", [])] or [1.0])
        stability = sum(var_sim) / len(var_sim)
        n_edges = rel.get("n_edges", 0)
        return {
            "source_originality": self._score(
                0.9 if var.get("clause_id", "").endswith(("0001", "0012")) else 0.6,
                "宋本底本直述（A 層原文）"),
            "transmission": self._score(
                min(1.0, n_comm / 9 * 0.7 + len(reception) / 6 * 0.3),
                f"{n_comm}/9 家注本承襲 + {len(reception)} 條全庫反響"),
            "variant_stability": self._score(
                stability, f"{n_var} 個異文版本，平均相似度 {round(stability, 3)}"),
            "commentary_dispute": self._score(
                dispute, f"注家術語分歧度 {round(dispute, 4)}（九注本對齊層計量）"),
            "fangzheng_expansion": self._score(
                min(1.0, n_edges / 12), f"關係圖譜 {n_edges} 條邊（類方/傳變/鑒別）"),
            "modern_translation": self._modern_translation_score(var["base_text"]),
            "evidence_reliability": self._score(
                min(1.0, 0.5 + n_comm / 18 + n_var / 10),
                f"原文 A + {n_comm} 注家 C + {n_var} 異文 B 交叉印證"),
        }

    def _formula_influence(self, fr, grade: Dict, reception: List[Dict]) -> Dict:
        n_mod = len(fr.modification_relations or [])
        n_supp = len(fr.supporting_clauses or [])
        return {
            "source_originality": self._score(0.85, "見於傷寒論方證條文（A 層）"),
            "transmission": self._score(
                min(1.0, n_supp / 10 * 0.6 + len(reception) / 6 * 0.4),
                f"{n_supp} 條方證條文 + {len(reception)} 條全庫反響"),
            "relation_grade": {"grade": grade["grade"],
                               "relation": grade["relation"],
                               "basis": grade["basis"]},
            "fangzheng_expansion": self._score(
                min(1.0, n_mod / 8),
                f"衍生 {n_mod} 個加減/類方（方族 {fr.formula_family}）"),
            "modern_translation": self._modern_translation_score(
                "、".join(fr.core_symptoms[:6])),
            "evidence_reliability": self._score(
                min(1.0, 0.55 + n_supp / 20),
                f"方證分級 {grade['grade']} + {n_supp} 條支撐"),
        }

    def _concept_influence(self, direct: List[Dict], reception: List[Dict],
                           evolution: List[Dict]) -> Dict:
        has_modern = any(s["stage"] == "現代轉化" for s in evolution)
        return {
            "source_originality": self._score(
                0.6 if direct else 0.2,
                "傷寒論原文直述" if direct else "傷寒論未直述（源頭 deferred）"),
            "transmission": self._score(
                min(1.0, len(reception) / 6), f"{len(reception)} 條全庫後世反響"),
            "modern_translation": self._score(
                0.8 if has_modern else 0.2,
                "已映射現代疾病（候選）" if has_modern else "暫無現代映射"),
            "evidence_reliability": self._score(
                0.6 if direct else 0.35,
                "原文 + 後世交叉" if direct else "以後世反響與現代映射為主"),
        }

    def _modern_translation_score(self, text: str) -> Dict:
        for concept, aliases in CONCEPT_ALIASES.items():
            if any(a in text for a in aliases):
                mm = self._modern_mapping(concept, aliases)
                if mm:
                    return self._score(
                        {"A": 0.9, "B": 0.7, "C": 0.5, "D": 0.4}.get(
                            mm.get("grade", "D"), 0.4),
                        f"映射現代疾病「{mm['modern']}」（{mm.get('grade')} 級候選）")
        return self._score(0.15, "暫無現代疾病映射")

    @staticmethod
    def _score(value: float, basis: str) -> Dict:
        value = max(0.0, min(1.0, round(value, 3)))
        return {"value": value, "band": _band(value), "basis": basis}

    # ── helpers ————————————————————————————————————————
    @staticmethod
    def _clause_divergence(div: Dict, clause_id: str) -> Optional[Dict]:
        for c in div.get("clauses", []):
            if c.get("clause_id") == clause_id:
                return c
        return None

    @staticmethod
    def _variant_note(var: Dict) -> str:
        n = var.get("n_variants", 0)
        if not n:
            return "未見版本異文（宋本孤證或他本缺載）"
        books = "、".join(v["book"] for v in var.get("variants", []))
        sims = [v["similarity"] for v in var.get("variants", [])]
        return (f"{n} 個他本異文（{books}）；相似度 "
                f"{min(sims)}–{max(sims)}——文字存在版本差異，非孤證")

    @staticmethod
    def _warning() -> str:
        return ("證據分層警示：原文直述（A）、注家解釋（C）、後世發揮（D）與"
                "現代疾病/機制映射（候選）須嚴格區分——古籍概念與現代疾病、"
                "分子機制不能機械等同（如「腎虛≠Wnt通路異常」「血瘀≠血栓」）；"
                "現代機制僅作表型/機制層面的解釋橋梁，不改變古籍概念的原義。")
