"""五類溯源鏈：結構化溯源報告生成。

| 鏈 | 回答 | 鏈路 |
|----|------|------|
| 原文溯源鏈 | 這句話從哪裡來 | 條文 → 異文 → 上下文 → 注家 → 後世引用 → 計量 → 現代 |
| 方劑源流鏈 | 這個方如何演變 | 首見條文 → 組成/劑量 → 類方演化 → 方名傳播 → 方證觀點 |
| 方證觀點鏈 | 某方為何對應某證 | 原文直述檢驗 → 注家首倡時間線 → 學派立場 → 現代回聲 |
| 注家解釋鏈 | 後世如何解釋原文 | 注家 → 學派 → 對齊覆蓋 → 術語指紋 → 被轉引樞紐度 |
| 學派觀點鏈 | 不同學派為何不同 | 範式 → 成員著作 → 派內/跨派一致度 → 對立學派 |

每份報告攜帶 evidence_grade（實際用到的證據層）與 warnings（後世歸納
與原文直述的區分提示），所有 clause_id 可被 CitationGuard 逐字核驗。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from .. import config
from ..schemas import read_jsonl
from ..textutil import fold_variants, normalize_query
from . import builder
from .ids import dynasty_order
from .modern import modern_echo_for

EXCERPT = 80

RE_NUM = re.compile(r"^\d{1,4}$")


# ---------------------------------------------------------------------------
# 公共取數
# ---------------------------------------------------------------------------
def _clauses() -> Dict[str, Dict]:
    return {c["clause_id"]: c for c in read_jsonl(config.CLAUSE_DIR / "clauses.jsonl")}


def _resolve_clause(ref: str, clauses: Dict[str, Dict]) -> Optional[Dict]:
    ref = (ref or "").strip()
    if ref in clauses:
        return clauses[ref]
    m = RE_NUM.match(ref.lstrip("第").rstrip("條条"))
    if m:
        cid = config.ID_PREFIX_CLAUSE + f"{int(m.group(0)):04d}"
        return clauses.get(cid)
    return None


def _citations_by_dynasty(clause_ids: List[str], max_books: int = 6) -> Dict:
    """（著作,條文）聚合邊 → 按朝代分組的引用概覽。"""
    wanted = set(clause_ids)
    rows = [r for r in builder.load_agg_edges() if r["clause_id"] in wanted]
    by_dyn: Dict[str, Dict] = {}
    for r in rows:
        dyn = r["dynasty"] or "未詳"
        s = by_dyn.setdefault(dyn, {"dynasty": dyn,
                                    "dynasty_order": dynasty_order(dyn),
                                    "books": {}})
        b = s["books"].setdefault(r["book_dir"], {
            "book": r["book"], "author": r["author"], "n_paragraphs": 0,
            "modes": {}, "max_coverage": 0.0})
        b["n_paragraphs"] += r["n_paragraphs"]
        b["max_coverage"] = max(b["max_coverage"], r["max_coverage"])
        for m, n in r["modes"].items():
            b["modes"][m] = b["modes"].get(m, 0) + n
    out = []
    for dyn in sorted(by_dyn, key=lambda d: (by_dyn[d]["dynasty_order"], d)):
        s = by_dyn[dyn]
        books = sorted(s["books"].values(),
                       key=lambda b: (-b["n_paragraphs"], b["book"]))
        out.append({"dynasty": dyn, "n_books": len(books),
                    "books": [{**b, "modes": {m: b["modes"][m]
                                              for m in sorted(b["modes"])}}
                              for b in books[:max_books]]})
    return {"n_citing_books": len({b for d in by_dyn.values() for b in d["books"]}),
            "by_dynasty": out}


def _main_path(clause_id: str) -> List[Dict]:
    per_dyn: Dict[str, Dict] = {}
    for r in builder.load_agg_edges():
        if r["clause_id"] != clause_id:
            continue
        dyn = r["dynasty"] or "未詳"
        cur = per_dyn.get(dyn)
        key = (r["max_coverage"], r["max_run"])
        if cur is None or key > (cur["max_coverage"], cur["max_run"]):
            per_dyn[dyn] = {"dynasty": dyn, "dynasty_order": dynasty_order(dyn),
                            "book": r["book"], "author": r["author"],
                            "max_coverage": r["max_coverage"],
                            "max_run": r["max_run"]}
    chain = sorted(per_dyn.values(), key=lambda x: (x["dynasty_order"], x["book"]))
    return ([{"dynasty": "東漢", "book": "傷寒論", "author": "張仲景",
              "max_coverage": 1.0, "max_run": 0}] + chain)


def _commentaries_for(clause_id: str, schools_reg: Dict) -> List[Dict]:
    rows = []
    seen = set()
    member_school = schools_reg.get("commentator_school", {})
    registry = builder.load_registry()
    dyn_of_dir = {w["book_dir"]: w["dynasty"] for w in registry["works"]}
    for r in read_jsonl(config.RULES_COMMENTARY_DIR / "commentary_rules.jsonl"):
        if r.get("clause_id") != clause_id:
            continue
        commentator = r.get("commentator", "")
        if commentator in seen:
            continue
        seen.add(commentator)
        dyn = dyn_of_dir.get(r.get("book", ""), "")
        rows.append({"commentator": commentator, "book": r.get("book", ""),
                     "dynasty": dyn, "dynasty_order": dynasty_order(dyn),
                     "school_id": member_school.get(commentator, ""),
                     "excerpt": r.get("commentary_text", "")[:EXCERPT]})
    rows.sort(key=lambda x: (x["dynasty_order"], x["commentator"]))
    return rows


# ---------------------------------------------------------------------------
# 1. 原文溯源鏈
# ---------------------------------------------------------------------------
def clause_chain(ref: str) -> Dict:
    clauses = _clauses()
    c = _resolve_clause(ref, clauses)
    if c is None:
        return {"error": f"未找到條文 {ref}（可用條文號 1-398 或 clause_id）"}
    cid = c["clause_id"]
    schools_reg = builder.load_schools()

    variants = [v for v in read_jsonl(config.RULES_VARIANT_DIR / "variant_rules.jsonl")
                if v.get("clause_id") == cid]
    n = c.get("clause_number", 0)
    prev_id = config.ID_PREFIX_CLAUSE + f"{n-1:04d}" if n > 1 else ""
    next_id = config.ID_PREFIX_CLAUSE + f"{n+1:04d}" if 0 < n < 398 else ""
    commentaries = _commentaries_for(cid, schools_reg)
    citations = _citations_by_dynasty([cid])
    network = builder.load_network()
    bursts = [b for b in network.get("bursts", []) if b["clause_id"] == cid]
    modern = modern_echo_for([cid])

    grade = ["A 原文直述"]
    if variants:
        grade.append("B 版本異文")
    if commentaries:
        grade.append("C 注家解釋")
    if citations["n_citing_books"]:
        grade.append("後世引文邊（逐字回源）")
    if modern.get("available") and modern.get("n_citations"):
        grade.append("現代學術引用（導入層）")

    return {
        "chain_type": "原文溯源鏈",
        "query": ref,
        "clause": {"clause_id": cid, "clause_number": n,
                   "chapter": c.get("chapter", ""),
                   "six_channel": c.get("six_channel", ""),
                   "text": c.get("clean_text", "")},
        "variants": [{"variant_book": v.get("variant_book", ""),
                      "similarity": v.get("similarity", 0.0),
                      "notable_differences": v.get("notable_differences", []),
                      "variant_text": v.get("variant_text", "")[:EXCERPT]}
                     for v in variants],
        "context": {"prev_clause_id": prev_id if prev_id in clauses else "",
                    "next_clause_id": next_id if next_id in clauses else ""},
        "commentaries": commentaries,
        "citations": citations,
        "main_path": _main_path(cid),
        "bursts": bursts,
        "modern": modern,
        "evidence_grade": grade,
        "section_evidence_levels": {
            "clause": "A 原文直述",
            "variants": "B 版本異文",
            "context": "A 原文直述（篇次相鄰）",
            "commentaries": "C 注家解釋",
            "citations": "引文邊（跨書逐字回源）",
            "main_path": "計量推導（基於引文邊）",
            "bursts": "計量推導（基於引文邊）",
            "modern": "現代導入層（用戶自備，不隨庫分發）",
        },
        "warnings": ["注家解釋與後世引用均屬 C/D 層，不得回填為原文直述；"
                     "「化用/暗引」為逐字片段證據，改寫判定僅為相似度提示。"],
    }


# ---------------------------------------------------------------------------
# 2. 方劑源流鏈
# ---------------------------------------------------------------------------
def formula_chain(name: str) -> Dict:
    q = normalize_query(name)
    rules = read_jsonl(config.RULES_FORMULA_DIR / "formula_pattern_rules.jsonl")
    rule = next((r for r in rules if fold_variants(r.get("formula", "")) == q), None)
    if rule is None:
        rule = next((r for r in rules if q and q in fold_variants(r.get("formula", ""))), None)
    if rule is None:
        return {"error": f"未找到方劑 {name}"}
    formula = rule["formula"]
    supporting = rule.get("supporting_clauses", [])

    # 劑量與類方演化（劑量計量層資產）
    ratios = {}
    ratios_path = config.RESEARCH_DIR / "dose_ratios.json"
    if ratios_path.exists():
        data = json.loads(ratios_path.read_text(encoding="utf-8"))
        ratios = next((r for r in data.get("formulas", [])
                       if r.get("formula") == formula), {})
    evolution = []
    evo_path = config.RESEARCH_DIR / "dose_family_evolution.json"
    if evo_path.exists():
        data = json.loads(evo_path.read_text(encoding="utf-8"))
        evolution = [e for e in data.get("edges", [])
                     if formula in (e.get("base", ""), e.get("modified", ""))]

    mentions = next((f for f in builder.load_formula_mentions().get("formulas", [])
                     if f.get("formula") == formula), None)
    mention_rows = []
    if mentions:
        mention_rows = sorted(
            mentions["by_book"],
            key=lambda b: (dynasty_order(b.get("dynasty", "")), b.get("book_dir", "")))

    claims = [c for c in builder.load_claims().get("claims", [])
              if c.get("formula") == formula]
    citations = _citations_by_dynasty(supporting)
    modern = modern_echo_for(supporting)
    anchor = supporting[0] if supporting else ""
    schools_reg = builder.load_schools()

    return {
        "chain_type": "方劑源流鏈",
        "query": name,
        "formula": formula,
        "earliest_source": {"work": "傷寒論（宋本）", "clause_ids": supporting,
                            "core_pattern": rule.get("core_pattern", "")},
        "composition": rule.get("composition", []),
        "administration_notes": rule.get("administration_notes", [])[:3],
        "dose_ratios": ratios,
        "modification_relations": rule.get("modification_relations", []),
        "family_dose_evolution": evolution,
        "name_transmission": {"total_mentions": (mentions or {}).get("total_mentions", 0),
                              "n_books": (mentions or {}).get("n_books", 0),
                              "by_book": mention_rows[:15]},
        "claims": [{"claim_id": c["claim_id"], "claim": c["claim"],
                    "evidence_grade": c["evidence_grade"]} for c in claims],
        "anchor_commentaries": _commentaries_for(anchor, schools_reg)[:6] if anchor else [],
        "citations_of_clauses": citations,
        "modern": modern,
        "evidence_grade": ["A 原文直述（條文與組成）", "D 劑量/類方計量",
                           "方名逐字計量", "後世引文邊"],
        "section_evidence_levels": {
            "earliest_source": "A 原文直述",
            "composition": "A 原文直述（<F> 方塊）",
            "administration_notes": "A 原文直述",
            "dose_ratios": "A 銖當量藥量比（克數折算屬 D 層假設）",
            "modification_relations": "D 類方歸納",
            "family_dose_evolution": "D 劑量計量歸納",
            "name_transmission": "方名逐字計量（跨書）",
            "claims": "方證觀點（分級見各條 evidence_grade）",
            "anchor_commentaries": "C 注家解釋",
            "citations_of_clauses": "引文邊（跨書逐字回源）",
            "modern": "現代導入層（用戶自備，不隨庫分發）",
        },
        "warnings": ["主治演變與方義解釋屬注文層歸納；方名計量為逐字統計，"
                     "不含異名（異名歸併屬後續工作，如實聲明）。"],
    }


# ---------------------------------------------------------------------------
# 3. 方證觀點演化鏈
# ---------------------------------------------------------------------------
def claim_chain(key: str) -> Dict:
    q = normalize_query(key)
    claims = builder.load_claims().get("claims", [])
    claim = next((c for c in claims if c["claim_id"] == key), None)
    if claim is None:
        claim = next((c for c in claims
                      if q and (q in fold_variants(c["formula"])
                                or q in fold_variants(c["claim"]))), None)
    if claim is None:
        available = [c["claim_id"] + " " + c["claim"] for c in claims]
        return {"error": f"未找到方證觀點 {key}", "available_claims": available}

    schools_reg = builder.load_schools()
    school_names = {s["school_id"]: s["name"] for s in schools_reg.get("schools", [])}
    citations = _citations_by_dynasty(claim.get("classical_evidence", []))
    modern = modern_echo_for(claim.get("classical_evidence", []))
    return {
        "chain_type": "方證觀點演化鏈",
        "query": key,
        **claim,
        "school_views_named": [{"school_id": s, "name": school_names.get(s, s)}
                               for s in claim.get("school_views", [])],
        "citations_of_evidence": citations,
        "modern": modern,
        "section_evidence_levels": {
            "classical_evidence": "A 原文條文（clause_id）",
            "terms_verbatim_in_original": "A 原文逐字檢驗",
            "commentarial_chronology": "C 注家解釋（按朝代排序）",
            "school_views_named": "posthoc_induction 學派歸納",
            "controversies": "posthoc_induction 編輯性整理",
            "citations_of_evidence": "引文邊（跨書逐字回源）",
            "modern": "現代導入層（用戶自備，不隨庫分發）",
        },
        "warnings": [claim.get("warning", ""),
                     "多觀點並存：學派立場不做對錯裁決。"],
    }


# ---------------------------------------------------------------------------
# 4. 注家解釋鏈
# ---------------------------------------------------------------------------
def commentator_chain(name: str) -> Dict:
    q = normalize_query(name)
    schools_reg = builder.load_schools()
    member_school = schools_reg.get("commentator_school", {})
    match = next((c for c in sorted(member_school)
                  if q and q in fold_variants(c)), None)
    atlas_path = config.RESEARCH_DIR / "commentary_divergence.json"
    atlas = (json.loads(atlas_path.read_text(encoding="utf-8"))
             if atlas_path.exists() else {})
    coverage = [
        {"book": b, **info} for b, info in sorted(atlas.get("book_coverage", {}).items())
        if q and q in fold_variants(info.get("commentator", ""))]
    if match is None and not coverage:
        return {"error": f"未找到注家 {name}",
                "known_commentators": sorted(member_school)}
    commentator = match or coverage[0]["commentator"]
    school_id = member_school.get(commentator, "")
    school = next((s for s in schools_reg.get("schools", [])
                   if s["school_id"] == school_id), None)

    fingerprints = atlas.get("commentator_fingerprints", {}).get(commentator, [])
    agreements = [row for row in atlas.get("agreement_matrix", [])
                  if commentator in (row.get("a"), row.get("b"))]
    agreements.sort(key=lambda r: -r.get("mean_term_agreement", 0.0))

    # 被轉引樞紐度：後世著作經由該注家注文轉引的計量
    relayed = [r for r in builder.load_relay_edges()
               if r.get("via_commentator") == commentator]
    relayed.sort(key=lambda r: (-r["n_paragraphs"], r["book_dir"]))

    return {
        "chain_type": "注家解釋鏈",
        "query": name,
        "commentator": commentator,
        "school": ({"school_id": school_id, "name": school["name"],
                    "paradigm": school["paradigm"]} if school else {}),
        "aligned_books": coverage,
        "fingerprint_terms": fingerprints[:10],
        "agreement_with_peers": agreements[:6],
        "relay_hub": {"n_relaying_books": len({r["book_dir"] for r in relayed}),
                      "top": [{"book": r["book"], "dynasty": r["dynasty"],
                               "n_paragraphs": r["n_paragraphs"]}
                              for r in relayed[:8]]},
        "evidence_grade": ["C 注家解釋（條文級對齊）", "轉引邊（逐字回源）",
                           "學派歸屬（posthoc_induction）"],
        "section_evidence_levels": {
            "aligned_books": "C 注家對齊（計算資產）",
            "fingerprint_terms": "C 層計算資產（詞彙 lift）",
            "agreement_with_peers": "C 層計算資產（實測一致度）",
            "relay_hub": "轉引邊（跨書逐字回源）",
            "school": "posthoc_induction 學派歸納",
        },
        "warnings": ["注家指紋與一致度為 C 層計算資產；學派歸屬為編輯性元數據。"],
    }


# ---------------------------------------------------------------------------
# 5. 學派觀點鏈
# ---------------------------------------------------------------------------
def school_chain(key: str) -> Dict:
    q = normalize_query(key)
    schools_reg = builder.load_schools()
    schools = schools_reg.get("schools", [])
    school = next((s for s in schools if s["school_id"] == key), None)
    if school is None:
        school = next((s for s in schools
                       if q and (q in fold_variants(s["name"])
                                 or any(q in fold_variants(m["name"])
                                        for m in s["members"]))), None)
    if school is None:
        return {"error": f"未找到學派 {key}",
                "available_schools": [{"school_id": s["school_id"], "name": s["name"]}
                                      for s in schools]}
    school_names = {s["school_id"]: s["name"] for s in schools}
    network = builder.load_network()
    breadth = {w["book_dir"]: w for w in network.get("citing_works", [])}
    member_works = []
    for m in school["members"]:
        for bdir in m["book_dirs"]:
            w = breadth.get(bdir)
            member_works.append({
                "member": m["name"], "book_dir": bdir,
                "n_clauses_cited": (w or {}).get("n_clauses_cited", 0),
                "n_edges": (w or {}).get("n_edges", 0)})
    return {
        "chain_type": "學派觀點鏈",
        "query": key,
        **{k: school[k] for k in ("school_id", "name", "paradigm", "scope",
                                  "members", "agreement", "source_level")},
        "opposed_to": [{"school_id": s, "name": school_names.get(s, s)}
                       for s in school.get("opposed_to", [])],
        "member_citation_breadth": member_works,
        "basis": schools_reg.get("note", ""),
        "section_evidence_levels": {
            "paradigm": "posthoc_induction 學派歸納",
            "members": "posthoc_induction（僅收語料在庫著者）",
            "agreement": "C 層實測一致度（分歧圖譜）",
            "member_citation_breadth": "引文邊計量",
        },
        "warnings": ["學派歸屬為後世歸納（posthoc_induction）；"
                     "一致度證據來自注家分歧圖譜實測。"],
    }


# ---------------------------------------------------------------------------
# 6. 任意文本回源（原文溯源鏈入口）
# ---------------------------------------------------------------------------
def text_trace(text: str) -> Dict:
    matcher = builder.get_matcher()
    matches = matcher.match_text(normalize_query(text), limit=5)
    if not matches:
        out = {"chain_type": "原文溯源鏈", "query": text,
               "matches": [],
               "note": "傷寒論條文（含輔助篇章）內無可回源匹配；"
                       "該句可能出自他書（如《內經》）或為後世歸納語。"}
        out["library_candidates"] = _library_candidates(text)
        return out
    best = matches[0]
    chain = clause_chain(best["clause_id"])
    chain["query"] = text
    chain["matches"] = matches
    return chain


def _library_candidates(text: str, limit: int = 6) -> Dict:
    """傷寒論內無匹配時，退到中醫笈成全庫（若已下載）找候選出處。

    只做逐字全文檢索並回報「書·章節」定位（文獻旁證層），不臆斷首出。"""
    from ..corpus import library
    if not library.is_available():
        return {"available": False,
                "note": "全庫未下載（`library fetch` 後，可在 800+ 部醫籍中"
                        "檢索該句的候選出處）。"}
    q = normalize_query(text)
    q = "".join(ch for ch in q if "㐀" <= ch <= "鿿")[:20]
    if len(q) < 4:
        return {"available": True, "hits": [],
                "note": "查詢過短，不作全庫檢索。"}
    res = library.Library().grep(q, limit=limit)
    return {"available": True,
            "query": q,
            "n_hits": res.get("n_hits", 0),
            "scan_capped": res.get("scan_capped", False),
            "hits": [{k: h.get(k, "") for k in
                      ("title", "author", "dynasty", "category", "section")}
                     for h in res.get("hits", [])],
            "note": "文獻旁證層：按書·章節定位候選出處，需人工核對；"
                    "全庫檢索不臆斷「最早出處」（庫外文獻與版本先後未覆蓋）。"}


def trace_dispatch(query_type: str, ref: str) -> Dict:
    """統一入口（CLI / 工具 / 服務端共用）。"""
    dispatch = {"clause": clause_chain, "formula": formula_chain,
                "claim": claim_chain, "school": school_chain,
                "commentator": commentator_chain, "text": text_trace}
    fn = dispatch.get(query_type)
    if fn is None:
        return {"error": f"未知溯源對象類型 {query_type}",
                "supported": sorted(dispatch)}
    return fn(ref)
