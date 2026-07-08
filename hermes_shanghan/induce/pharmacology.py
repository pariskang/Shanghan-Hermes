"""藥解/方解 — 規則與模型各守其位的混合推理.

分工鐵律（回應「單獨一方都不能佔比過高」）：

  規則層（確定性，永遠在場）
    · 語料內證統計：某藥見於哪些方（A 錨定 clause_id）、典型劑量與炮製、
      高頻藥對（跨方共現，可數的事實）；
    · 本草種子詞典：性味/功效/類別/毒性（D 層通識，herb_lexicon）；
    · 君臣佐使候選：方名藥→主藥、銖權重排序、調和之品→佐使——
      推導方法全程可見，標 D/E 層 + 置信度，絕不冒充原文；
    · 安全審校：毒性/妊娠/十八反強制掃描。

  模型層（可用時，證據約束下自主判斷）
    · 在證據 JSON 邊界內覆核/調整角色判定（輸出標 E 層 + 理由）；
    · 撰寫方義解釋文本，過 CitationGuard（引用僅限本輪證據）；
    · 失敗/離線 → 確定性模板，同一代碼路徑。

輸出：單味藥知識卡（HerbCard）與方劑知識卡（FormulaCard = 組成+藥解+
君臣佐使+配伍+病機治法+方義+煎服法+安全+證據鏈）。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Dict, List, Optional

from .. import herb_lexicon, lexicon
from ..textutil import normalize_query
from .decoction import parse_decoction

_ROLE_ADJUVANTS = ("甘草", "大棗", "生薑", "粳米", "食蜜")   # 調和/護中之品


# ═══════════════════════════════════════════════════════════════════
class PharmacopoeiaIndex:
    """語料內證索引：herb → 方劑/劑量/炮製/共現；formula → 方後原文塊."""

    def __init__(self, clauses):
        self.herb: Dict[str, Dict] = {}
        self.blocks: Dict[str, Dict] = {}          # formula → block info
        for c in clauses:
            for b in (c.formula_blocks or []):
                fname = lexicon.canonical_formula(normalize_query(b.formula_name))
                blk = {"clause_id": c.clause_id,
                       "composition": b.composition,
                       "preparation": b.preparation or "",
                       "administration": b.administration or ""}
                old = self.blocks.get(fname)
                # 同方多見時取方後最完整的一塊
                if old is None or len(blk["preparation"]) > len(old["preparation"]):
                    self.blocks[fname] = blk
                herbs_here = [herb_lexicon.canonical_herb(x["herb"])
                              for x in b.composition]
                for x in b.composition:
                    h = herb_lexicon.canonical_herb(x["herb"])
                    e = self.herb.setdefault(
                        h, {"formulas": [], "freq": 0,
                            "co_herbs": Counter(), "processing": Counter()})
                    e["freq"] += 1
                    if len(e["formulas"]) < 40:
                        e["formulas"].append(
                            {"formula": fname,
                             "dose_processing": x["dose_processing"],
                             "clause_id": c.clause_id})
                    proc = self._processing(x["dose_processing"])
                    if proc:
                        e["processing"][proc] += 1
                    for other in herbs_here:
                        if other != h:
                            e["co_herbs"][other] += 1

    @staticmethod
    def _processing(dose_processing: str) -> str:
        m = re.search(r"[，,](.+)$", dose_processing or "")
        return m.group(1).strip() if m else ""

    def inventory(self) -> List[str]:
        return sorted(self.herb)

    def resolve_herb(self, name: str) -> Dict:
        """藥名歸一 + 模糊候選（與方名消歧同構）。"""
        raw = name.strip()
        cand = herb_lexicon.canonical_herb(normalize_query(raw))
        inv = self.inventory()
        if cand in inv:
            return {"input": raw, "resolved": cand, "ambiguous": False,
                    "candidates": []}
        scored = []
        for h in inv:
            if cand and cand in h:
                scored.append((1.0 + len(cand) / len(h), h))
                continue
            sa, sb = set(cand), set(h)
            if sa and sb and len(sa & sb) / len(sa | sb) >= 0.5:
                scored.append((len(sa & sb) / len(sa | sb), h))
        scored.sort(key=lambda t: (-t[0], len(t[1]), t[1]))
        candidates = [h for _, h in scored[:6]]
        if len(candidates) == 1:
            return {"input": raw, "resolved": candidates[0],
                    "ambiguous": False, "candidates": candidates}
        return {"input": raw, "resolved": None,
                "ambiguous": bool(candidates), "candidates": candidates}


# ═══════════════════════════════════════════════════════════════════
class HerbExplainer:
    """藥解：內證統計（A 錨定）+ 本草通識（D）+ 安全審校."""

    def __init__(self, index: PharmacopoeiaIndex):
        self.index = index

    def card(self, name: str) -> Dict:
        res = self.index.resolve_herb(name)
        if not res["resolved"]:
            return {"error": (f"藥名「{res['input']}」無法唯一定位"
                              if res["candidates"] else
                              f"傷寒論方藥中未見「{res['input']}」"),
                    "ambiguous": res["ambiguous"],
                    "candidates": res["candidates"]}
        h = res["resolved"]
        e = self.index.herb[h]
        seed = herb_lexicon.herb_info(h) or {}
        pairs = [{"paired_with": other, "n_formulas_together": n,
                  "example": next((f["formula"] for f in e["formulas"]
                                   if any(x["formula"] == f["formula"]
                                          for x in self.index.herb
                                          .get(other, {}).get("formulas", []))),
                                  "")}
                 for other, n in e["co_herbs"].most_common(6)]
        cautions = herb_lexicon.toxicity_flags([h])
        for a, group in herb_lexicon.SHIBAFAN_GROUPS:
            if h == a:
                cautions.append({"kind": "shibafan_doctrine", "herb": h,
                                 "note": f"後世十八反：{a}反{'、'.join(group)}"
                                         "（D 層法度，非傷寒論原文）"})
        return {
            "herb": h,
            "input": res["input"],
            "seed_knowledge": {          # 本草通識，明確標層
                "nature_flavor": seed.get("nature", "（種子詞典未收）"),
                "functions": seed.get("functions", []),
                "category": seed.get("category", ""),
                "layer": "D 本草學通識（神農本草經/名醫別錄通行認識），非傷寒論原文",
            },
            "corpus_evidence": {         # 傷寒論內證，A 錨定
                "n_formula_occurrences": e["freq"],
                "formulas": e["formulas"][:10],
                "processing_forms": [{"form": p, "n": n}
                                     for p, n in e["processing"].most_common(6)],
                "frequent_pairs": pairs,
                "layer": "A 內證統計（逐條可回源 clause_id）",
            },
            "cautions": cautions,
            "hint": "本草原文旁證可調 shanghan_library 檢索（如《本草綱目》）",
        }


# ═══════════════════════════════════════════════════════════════════
class FormulaExplainer:
    """方解：組成→藥解→角色推導→配伍→病機治法→方義→煎服法→安全→證據."""

    def __init__(self, index: PharmacopoeiaIndex, formula_rules,
                 therapy_rules=None, client=None):
        self.index = index
        self.rules = {r.formula: r for r in formula_rules}
        self.therapy = therapy_rules or []
        self.client = client

    # ------------------------------------------------------------------
    def explain(self, formula: str) -> Dict:
        fname = lexicon.canonical_formula(normalize_query(formula))
        blk = self.index.blocks.get(fname)
        rule = self.rules.get(fname)
        if blk is None:
            return {"error": f"未找到「{fname}」的方藥原文塊",
                    "hint": "可調 shanghan_list_formulas 查可用方名"}
        herbs = [herb_lexicon.canonical_herb(x["herb"])
                 for x in blk["composition"]]

        composition = self._composition_rows(blk)
        roles = self._roles(fname, composition)
        roles = self._llm_refine_roles(fname, composition, roles, rule)
        pairing = self._pairing(fname, herbs)
        patho = self._pathogenesis(fname, rule)
        deco = parse_decoction(fname, blk["preparation"],
                               blk["administration"], herbs,
                               clause_id=blk["clause_id"])
        prose = self._prose(fname, rule, composition, roles, patho)
        evidence = {"block_clause_id": blk["clause_id"],
                    "supporting_clauses": (rule.supporting_clauses[:6]
                                           if rule else []),
                    "note": "組成/煎服為 A 層方後原文；角色與病機為 D/E 層歸納"}
        return {
            "formula": fname,
            "source": "宋本《傷寒論》",
            "composition": composition,
            "roles": roles,
            "pairing": pairing,
            "pathogenesis_therapy": patho,
            "explanation": prose,
            "decoction": deco,
            "safety_flags": deco["safety_flags"],
            "evidence_trace": evidence,
            "modern_mapping": {"status": "deferred",
                               "note": "現代藥理/靶點/通路映射需外部證據庫，"
                                       "本系統不憑空生成（防 E 層冒充）"},
        }

    # ------------------------------------------------------------------
    def _composition_rows(self, blk) -> List[Dict]:
        from ..apps.dosimetry import parse_dose
        rows = []
        for x in blk["composition"]:
            h = herb_lexicon.canonical_herb(x["herb"])
            seed = herb_lexicon.herb_info(h) or {}
            dose_txt = (x["dose_processing"] or "").split("，")[0]
            parsed = parse_dose(dose_txt)
            rows.append({"herb": h,
                         "dose_processing": x["dose_processing"],
                         "zhu": parsed.get("zhu") if parsed.get("kind") == "weight" else None,
                         "functions": seed.get("functions", []),
                         "nature": seed.get("nature", "")})
        return rows

    def _roles(self, fname: str, composition: List[Dict]) -> Dict:
        """君臣佐使候選——傷寒論原文無此說，屬後世方論框架；本推導的每一步
        依據都寫明（方名藥/銖權重/調和之品），標 D/E 層。"""
        assign: List[Dict] = []
        named = [r["herb"] for r in composition if r["herb"] in fname]
        weights = {r["herb"]: r["zhu"] for r in composition if r["zhu"]}
        max_w = max(weights.values()) if weights else None
        for r in composition:
            h = r["herb"]
            if h in named:
                role, basis, conf = "君（主藥）", "方以藥名（如桂枝湯之桂枝）", 0.75
            elif max_w and weights.get(h) == max_w and h not in _ROLE_ADJUVANTS:
                # 方名藥已定君時，等權重之藥作臣而非並列君
                if named:
                    role, basis, conf = "臣（輔藥）", "銖權重與主藥相當", 0.55
                else:
                    role, basis, conf = "君（主藥）候選", "銖權重最重", 0.6
            elif h in _ROLE_ADJUVANTS:
                role, basis, conf = "佐使（調和護中）", "本草通識：調和之品", 0.55
            elif max_w and weights.get(h) and weights[h] >= 0.7 * max_w:
                role, basis, conf = "臣（輔藥）", "銖權重居前", 0.5
            else:
                role, basis, conf = "佐（兼制）", "劑量居後/計數類無權重", 0.45
            assign.append({"herb": h, "role": role, "basis": basis,
                           "confidence": conf})
        return {"assignments": assign,
                "layer": "D/E 後世方論框架推導（原文無君臣佐使明文），方法透明可審",
                "method": "方名藥→主藥；銖權重排序；調和之品→佐使"}

    def _llm_refine_roles(self, fname, composition, roles, rule) -> Dict:
        """證據約束下的模型自主判斷：模型只能在既有藥味內調整角色並給理由，
        調整結果標 E 層；離線/失敗保持確定性結果。"""
        if self.client is None or not getattr(self.client, "available", False):
            return roles
        try:
            evidence = {"formula": fname,
                        "composition": [{k: r[k] for k in
                                         ("herb", "dose_processing", "functions")}
                                        for r in composition],
                        "core_pattern": rule.core_pattern if rule else "",
                        "rule_based_roles": roles["assignments"]}
            out = self.client.json_complete(
                "任務：覆核《傷寒論》方劑的君臣佐使推導。只可對給定藥味調整"
                "角色，每個調整必須給一句依據（依證候/劑量/功效，不得引入"
                "外部藥物或臆造原文）。嚴格輸出 JSON："
                "{\"assignments\":[{\"herb\":\"…\",\"role\":\"…\","
                "\"basis\":\"…\"}]}，無需調整則原樣返回。",
                json.dumps(evidence, ensure_ascii=False), task="synthesize")
            adj = out.get("assignments") or []
            valid_herbs = {r["herb"] for r in composition}
            if adj and all(a.get("herb") in valid_herbs and a.get("role")
                           for a in adj):
                return {"assignments": [{"herb": a["herb"], "role": a["role"],
                                         "basis": a.get("basis", ""),
                                         "confidence": 0.65}
                                        for a in adj],
                        "layer": "E 模型在證據約束下覆核（規則候選為底），須醫師審讀",
                        "method": roles["method"] + " + LLM 覆核"}
        except Exception:
            pass
        return roles

    def _pairing(self, fname: str, herbs: List[str]) -> List[Dict]:
        """配伍分析：跨方共現是可數的事實（A 錨定統計），功效協同屬 D 層。"""
        out = []
        seen = set()
        for i, a in enumerate(herbs):
            ea = self.index.herb.get(a, {})
            for b in herbs[i + 1:]:
                key = tuple(sorted((a, b)))
                if key in seen:
                    continue
                seen.add(key)
                n = ea.get("co_herbs", {}).get(b, 0)
                if n < 3:
                    continue
                fa = herb_lexicon.herb_info(a) or {}
                fb = herb_lexicon.herb_info(b) or {}
                shared = sorted(set(fa.get("functions", []))
                                & set(fb.get("functions", [])))
                others = [f["formula"] for f in ea.get("formulas", [])
                          if f["formula"] != fname][:3]
                out.append({"pair": [a, b],
                            "n_formulas_together": n,
                            "also_seen_in": others,
                            "synergy_note": ("、".join(shared) + "（功效同向，D層）"
                                             if shared else
                                             "功效互補配對（D層歸納）"),
                            "layer": "共現為 A 錨定統計；協同解讀為 D 層"})
        out.sort(key=lambda x: -x["n_formulas_together"])
        return out[:6]

    def _pathogenesis(self, fname: str, rule) -> Dict:
        methods = [t.therapy_method for t in self.therapy
                   if getattr(t, "polarity", "") == "indicated"
                   and fname in getattr(t, "representative_formulas", [])]
        return {"core_pattern": (rule.core_pattern if rule else ""),
                "core_symptoms": (rule.core_symptoms[:6] if rule else []),
                "therapeutic_methods": methods[:3],
                "contraindications": (rule.contraindications[:3] if rule else []),
                "layer": "D 跨條歸納（錨定 A 層條文，見 evidence_trace）"}

    # ------------------------------------------------------------------
    def _prose(self, fname, rule, composition, roles, patho) -> str:
        if self.client is not None and getattr(self.client, "available", False):
            try:
                evidence = {"formula": fname, "roles": roles["assignments"],
                            "pathogenesis": patho,
                            "supporting_clauses": (rule.supporting_clauses[:4]
                                                   if rule else [])}
                text = self.client.complete(
                    "任務：據下方證據為《傷寒論》方劑寫 3-5 句方義解釋。"
                    "只可使用證據中的事實；引用條文附 clause_id（僅限證據內）；"
                    "君臣佐使屬後世歸納，行文須以「後世方論多以…」措辭，"
                    "不得寫成仲景原意。",
                    json.dumps(evidence, ensure_ascii=False),
                    task="synthesize").strip()
                if text:
                    return text + "（E 層模型撰寫，證據約束）"
            except Exception:
                pass
        parts = []
        lead = next((a for a in roles["assignments"] if "君" in a["role"]), None)
        if lead:
            fx = "、".join(next((r["functions"] for r in composition
                                 if r["herb"] == lead["herb"]), [])[:2])
            parts.append(f"後世方論多以{lead['herb']}為主藥（{lead['basis']}）"
                         + (f"，取其{fx}" if fx else ""))
        if patho["core_pattern"]:
            parts.append(f"整方對應{patho['core_pattern']}")
        if patho["therapeutic_methods"]:
            parts.append(f"治法歸{ '、'.join(patho['therapeutic_methods'])}"
                         "（治法規則層歸納）")
        adjs = [a["herb"] for a in roles["assignments"] if "佐使" in a["role"]]
        if adjs:
            parts.append(f"{'、'.join(adjs)}和中調藥")
        return "；".join(parts) + "。（D 層歸納模板；接入真模型可得證據約束的方義文本）"


# ═══════════════════════════════════════════════════════════════════
_INDEX: Optional[PharmacopoeiaIndex] = None


def get_index(clauses=None) -> PharmacopoeiaIndex:
    global _INDEX
    if _INDEX is None:
        if clauses is None:
            from ..orchestrator import Artifacts
            clauses = Artifacts().clauses
        _INDEX = PharmacopoeiaIndex(clauses)
    return _INDEX
