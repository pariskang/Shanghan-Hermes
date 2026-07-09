"""藥證檔案（C10 藥解）：單味藥在《傷寒論》中的可計算畫像。

全部字段由既有確定性資產推導：<F> 方塊組成（A 層）、劑量計量層、
方證規則、條文實體標註。刻意不做的事（如實聲明）：
藥性/功效解釋屬本草層與注文層，非傷寒論原文直述，本檔案不編造；
「角色變化」（君臣佐使）屬後世方論歸納，僅給出可計算的配伍事實。
"""
from __future__ import annotations

import json
from typing import Dict, List

from .. import config
from ..schemas import read_jsonl
from ..textutil import fold_variants, normalize_query


def herb_profile(name: str) -> Dict:
    q = normalize_query(name)
    formula_rules = read_jsonl(config.RULES_FORMULA_DIR / "formula_pattern_rules.jsonl")

    # 出現方劑 + 配伍網絡（同方共現計數）
    formulas: List[Dict] = []
    partners: Dict[str, int] = {}
    canonical_name = ""
    for r in formula_rules:
        herbs = [c.get("herb", "") for c in r.get("composition", [])]
        hit = next((h for h in herbs if fold_variants(h) == q
                    or q in fold_variants(h)), "")
        if not hit:
            continue
        canonical_name = canonical_name or hit
        formulas.append({"formula": r.get("formula", ""),
                         "supporting_clauses": r.get("supporting_clauses", [])[:3],
                         "core_pattern": r.get("core_pattern", "")[:40]})
        for h in herbs:
            if h and h != hit:
                partners[h] = partners.get(h, 0) + 1
    if not formulas:
        return {"error": f"未在方劑組成中找到藥物 {name}"}

    # 劑量計量層：劑量範圍與眾數
    dose_rows = []
    dose_path = config.RESEARCH_DIR / "dose_table.json"
    if dose_path.exists():
        table = json.loads(dose_path.read_text(encoding="utf-8"))
        dose_rows = [row for row in table.get("rows", [])
                     if fold_variants(row.get("herb", "")) == fold_variants(canonical_name)]
    weights = sorted({row.get("raw", "") for row in dose_rows if row.get("raw")})

    # 條文出現（實體標註層）
    clause_ids = []
    for c in read_jsonl(config.CLAUSE_DIR / "clauses.jsonl"):
        if any(fold_variants(h) == fold_variants(canonical_name)
               for h in c.get("herbs", [])):
            clause_ids.append(c["clause_id"])

    top_partners = sorted(partners.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return {
        "herb": canonical_name,
        "n_formulas": len(formulas),
        "formulas": formulas,
        "n_clauses": len(clause_ids),
        "clause_ids": clause_ids[:20],
        "dose_variants": weights[:15],
        "n_dose_records": len(dose_rows),
        "top_partners": [{"herb": h, "n_formulas_together": n}
                         for h, n in top_partners],
        "section_evidence_levels": {
            "formulas": "A 原文直述（<F> 方塊組成）",
            "clause_ids": "A 條文實體標註",
            "dose_variants": "A 原文劑量寫法（折算屬 D 層）",
            "top_partners": "同方共現計數（可計算事實）",
        },
        "warnings": ["藥性/功效解釋屬本草層與注文層，非傷寒論原文直述，"
                     "本檔案不編造；君臣佐使等角色歸納屬後世方論。"],
    }
