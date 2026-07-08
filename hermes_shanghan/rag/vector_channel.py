"""語義向量通道 — 可信底座/增益層雙軌的向量檢索.

雙後端，同一接口（與全庫 LLM 策略同構）：

  char-tfidf（可信底座，默認）
      字符二元 TF-IDF 餘弦——零依賴、確定性、離線可測；作為向量通道的
      兜底，保證代碼路徑在任何環境都走通。
  embeddings（增益層，可選）
      設置 ``HERMES_EMBED_MODEL``（如 openai/text-embedding-3-small，經
      litellm 調用）後啟用真神經向量：681 條條文嵌入一次性批量計算並
      持久化緩存（data/shanghan/research/clause_embeddings_<model>.json，
      按條文 sha 鍵控，語料變更自動失效重算），查詢僅需 1 次嵌入調用。
      調用失敗自動回退 char-tfidf，絕不讓檢索斷流。

`embed_fn` 可注入（tests 用假嵌入函數確定性驗證在線路徑）。
返回分值為組內歸一化的相對相關度（rank-preserving），
供 omni_search 作「語義向量」通道加權合流。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..textutil import normalize_query


def _bigrams(text: str) -> List[str]:
    t = normalize_query("".join(text.split()))
    return [t[i:i + 2] for i in range(len(t) - 1)] or list(t)


class VectorChannel:
    def __init__(self, clauses=None, embed_fn: Optional[Callable] = None,
                 cache_dir: Optional[Path] = None):
        if clauses is None:
            from ..orchestrator import Artifacts
            clauses = [c for c in Artifacts().clauses
                       if c.text_type == "original_clause"]
        self.docs = [{"clause_id": c.clause_id, "text": c.clean_text}
                     for c in clauses]
        self._embed_fn = embed_fn if embed_fn is not None \
            else self._resolve_embed_fn()
        self.backend = "embeddings" if self._embed_fn else "char-tfidf"
        self._cache_dir = cache_dir
        self._doc_vecs: Optional[List[Dict]] = None      # tfidf sparse
        self._doc_embs: Optional[List[List[float]]] = None
        self._idf: Dict[str, float] = {}

    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_embed_fn() -> Optional[Callable]:
        """真嵌入僅在顯式配置 HERMES_EMBED_MODEL 且 litellm 可用時啟用。"""
        model = os.environ.get("HERMES_EMBED_MODEL", "").strip()
        if not model:
            return None
        try:
            import litellm
        except ImportError:
            return None

        def fn(texts: List[str]) -> List[List[float]]:
            resp = litellm.embedding(model=model, input=texts)
            return [d["embedding"] for d in resp["data"]]

        fn.model = model                                  # type: ignore
        return fn

    # ------------------------------------------------------------------
    def search(self, query: str, top_k: int = 6) -> Dict:
        if self.backend == "embeddings":
            try:
                return self._search_embeddings(query, top_k)
            except Exception as exc:      # 增益層失敗 → 兜底，絕不斷流
                self.backend = "char-tfidf"
                out = self._search_tfidf(query, top_k)
                out["fallback_reason"] = f"{type(exc).__name__}: {exc}"[:80]
                return out
        return self._search_tfidf(query, top_k)

    # ------------------------------------------------------------------
    # char-bigram TF-IDF（確定性兜底）
    def _build_tfidf(self):
        if self._doc_vecs is not None:
            return
        df: Dict[str, int] = {}
        grams_per_doc = []
        for d in self.docs:
            grams = _bigrams(d["text"])
            grams_per_doc.append(grams)
            for g in set(grams):
                df[g] = df.get(g, 0) + 1
        n = len(self.docs)
        self._idf = {g: math.log(1 + n / c) for g, c in df.items()}
        self._doc_vecs = []
        for grams in grams_per_doc:
            vec: Dict[str, float] = {}
            for g in grams:
                vec[g] = vec.get(g, 0.0) + self._idf[g]
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self._doc_vecs.append({g: v / norm for g, v in vec.items()})

    def _search_tfidf(self, query: str, top_k: int) -> Dict:
        self._build_tfidf()
        qv: Dict[str, float] = {}
        for g in _bigrams(query):
            if g in self._idf:
                qv[g] = qv.get(g, 0.0) + self._idf[g]
        qn = math.sqrt(sum(v * v for v in qv.values())) or 1.0
        scored = []
        for d, dv in zip(self.docs, self._doc_vecs):
            s = sum(w * dv.get(g, 0.0) for g, w in qv.items()) / qn
            if s > 0:
                scored.append((s, d))
        scored.sort(key=lambda x: (-x[0], x[1]["clause_id"]))
        top = scored[:top_k]
        peak = top[0][0] if top else 1.0
        return {"backend": "char-tfidf",
                "hits": [{"clause_id": d["clause_id"], "text": d["text"],
                          "relevance": round(s / peak, 3)}
                         for s, d in top]}

    # ------------------------------------------------------------------
    # neural embeddings（增益層）
    def _cache_path(self) -> Path:
        from .. import config
        model = getattr(self._embed_fn, "model", "custom")
        safe = "".join(ch if ch.isalnum() else "_" for ch in model)[:48]
        root = self._cache_dir or config.RESEARCH_DIR
        return Path(root) / f"clause_embeddings_{safe}.json"

    def _corpus_sha(self) -> str:
        h = hashlib.sha256()
        for d in self.docs:
            h.update(d["clause_id"].encode())
            h.update(d["text"].encode())
        return h.hexdigest()[:16]

    def _load_doc_embeddings(self):
        if self._doc_embs is not None:
            return
        path = self._cache_path()
        sha = self._corpus_sha()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("corpus_sha") == sha:
                self._doc_embs = data["embeddings"]
                return
        embs: List[List[float]] = []
        B = 96                                     # 批量嵌入
        for i in range(0, len(self.docs), B):
            embs += self._embed_fn([d["text"] for d in self.docs[i:i + B]])
        self._doc_embs = embs
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"corpus_sha": sha,
             "model": getattr(self._embed_fn, "model", "custom"),
             "n": len(embs), "embeddings": embs}), encoding="utf-8")

    def _search_embeddings(self, query: str, top_k: int) -> Dict:
        self._load_doc_embeddings()
        qv = self._embed_fn([query])[0]
        qn = math.sqrt(sum(v * v for v in qv)) or 1.0
        scored = []
        for d, dv in zip(self.docs, self._doc_embs):
            dot = sum(a * b for a, b in zip(qv, dv))
            dn = math.sqrt(sum(v * v for v in dv)) or 1.0
            scored.append((dot / (qn * dn), d))
        scored.sort(key=lambda x: (-x[0], x[1]["clause_id"]))
        top = scored[:top_k]
        peak = top[0][0] if top and top[0][0] > 0 else 1.0
        return {"backend": "embeddings",
                "model": getattr(self._embed_fn, "model", "custom"),
                "hits": [{"clause_id": d["clause_id"], "text": d["text"],
                          "relevance": round(max(0.0, s / peak), 3)}
                         for s, d in top]}


_VECTOR: Optional[VectorChannel] = None


def get_vector_channel() -> VectorChannel:
    global _VECTOR
    if _VECTOR is None:
        _VECTOR = VectorChannel()
    return _VECTOR
