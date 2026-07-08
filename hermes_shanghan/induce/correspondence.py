"""方證對應引擎 — 從「推薦方」升級為「證明方證關係」.

核心原則（回應方案第一節）：方證對應不是方病對應。推理鏈是

    症狀組合 → 病機結構(D/E) → 治法(D) → 候選方 → 多維評分（透明分解）
    → 方證關係分級（原文標記推導）→ 類方鑒別 → 證據鏈 → 適用邊界

三個誠實性設計（對方案的修正）：
  * 病機術語（營衛不和等）屬後世歸納——PATHOGENESIS_MAP 每條標 D/E 層，
    絕不寫成仲景原意；
  * 方證關係分級不靠模型判斷，而從宋本原文標記確定性推導：
    主之→直接方證(A)、宜/屬→方症證據(B)、與/可與→試用性方證(B-)、
    無原文標記→類方/歸納(D)——143 條「主之」是可數的事實；
  * 宋本無舌診主證體系（舌診成熟於後世），畫像與評分**不設舌象維度**，
    顯式缺位聲明——不為湊維度而虛構知識。

方證畫像（FormulaProfile）= 匹配導向的知識資產：核心證/兼證/排除證
（互斥證對推導）/病機候選(D)/治法/關係分級/煎服要點/類方——全部從
既有規則層自動裝配，逐項可回源。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .. import config, lexicon
from ..schemas import read_jsonl
from ..textutil import normalize_query

# ═══════════════════════════════════════════════════════════════════
# 病機推理表（D/E 層後世歸納；required 至少中一、excluded 見則否決）
# ═══════════════════════════════════════════════════════════════════
PATHOGENESIS_NOTE = ("病機結構屬後世歸納（D/E 層），非宋本原文用語；"
                     "推理依據（命中/缺失/排除）逐項可見。")

PATHOGENESIS_MAP: List[Dict] = [
    {"pathogenesis": "營衛不和（表虛）", "channel": "太陽病",
     "required": ["汗出", "自汗出"], "supporting": ["惡風", "發熱", "頭痛", "鼻鳴", "乾嘔"],
     "pulse": ["浮緩", "緩", "陽浮而陰弱"], "excluded": ["無汗"],
     "method": "汗法", "method_label": "解肌祛風、調和營衛"},
    {"pathogenesis": "風寒束表（表實）", "channel": "太陽病",
     "required": ["無汗"], "supporting": ["惡寒", "發熱", "身疼痛", "骨節疼痛", "喘", "頭痛"],
     "pulse": ["浮緊", "緊"], "excluded": ["汗出", "自汗出"],
     "method": "汗法", "method_label": "發汗解表、宣肺平喘"},
    {"pathogenesis": "外寒內熱（表實兼煩躁）", "channel": "太陽病",
     "required": ["煩躁"], "supporting": ["發熱", "惡寒", "身疼痛", "無汗"],
     "pulse": ["浮緊"], "excluded": ["汗出"],
     "method": "汗法", "method_label": "發汗解表、兼清鬱熱"},
    {"pathogenesis": "邪熱壅肺", "channel": "太陽病",
     "required": ["喘"], "supporting": ["汗出", "發熱", "無大熱", "咳"],
     "pulse": [], "excluded": ["惡寒踡臥"],
     "method": "清法", "method_label": "清宣肺熱、降氣平喘"},
    {"pathogenesis": "陽明氣分熱盛", "channel": "陽明病",
     "required": ["大煩渴不解", "煩渴", "大渴", "渴欲飲水"],
     "supporting": ["發熱", "汗出", "惡熱", "面赤"],
     "pulse": ["洪大", "滑"], "excluded": ["惡寒"],
     "method": "清法", "method_label": "清熱生津"},
    {"pathogenesis": "陽明腑實（燥屎內結）", "channel": "陽明病",
     "required": ["不大便", "大便硬", "燥屎"],
     "supporting": ["潮熱", "譫語", "腹滿", "腹脹滿", "手足濈然汗出"],
     "pulse": ["沉實", "實"], "excluded": ["下利清穀"],
     "method": "下法", "method_label": "攻下實熱、蕩滌燥結"},
    {"pathogenesis": "少陽樞機不利", "channel": "少陽病",
     "required": ["往來寒熱", "胸脅苦滿", "口苦"],
     "supporting": ["默默不欲飲食", "心煩喜嘔", "咽乾", "目眩", "嘔"],
     "pulse": ["弦", "弦細"], "excluded": [],
     "method": "和法", "method_label": "和解少陽、疏利樞機"},
    {"pathogenesis": "水飲內停（氣化不利）", "channel": "太陽病",
     "required": ["小便不利", "渴欲飲水", "水入則吐"],
     "supporting": ["發熱", "煩渴", "頭眩", "心下悸", "臍下悸"],
     "pulse": ["浮"], "excluded": [],
     "method": "利水", "method_label": "化氣行水"},
    {"pathogenesis": "水氣凌心（陽虛飲動）", "channel": "太陽病",
     "required": ["心下悸", "頭眩", "身瞤動"],
     "supporting": ["心下逆滿", "氣上衝", "振振欲擗地", "小便不利"],
     "pulse": ["沉緊"], "excluded": [],
     "method": "溫法", "method_label": "溫陽化飲"},
    {"pathogenesis": "熱擾胸膈（虛煩）", "channel": "太陽病",
     "required": ["虛煩不得眠", "心中懊憹"],
     "supporting": ["煩熱", "胸中窒", "反覆顛倒"],
     "pulse": [], "excluded": ["下利清穀"],
     "method": "吐法", "method_label": "清宣鬱熱、除煩"},
    {"pathogenesis": "水熱互結（結胸）", "channel": "太陽病",
     "required": ["結胸", "心下痛"], "supporting": ["按之石硬", "短氣", "潮熱"],
     "pulse": ["沉緊"], "excluded": [],
     "method": "下法", "method_label": "瀉熱逐水破結"},
    {"pathogenesis": "寒熱錯雜痞", "channel": "太陽病",
     "required": ["心下痞", "心下痞硬"],
     "supporting": ["嘔", "腸鳴", "下利", "乾噫食臭"],
     "pulse": [], "excluded": ["心下痛"],
     "method": "和法", "method_label": "辛開苦降、和胃消痞"},
    {"pathogenesis": "太陰虛寒（脾陽不足）", "channel": "太陰病",
     "required": ["腹滿", "自利", "下利"],
     "supporting": ["腹痛", "不渴", "食不下", "吐"],
     "pulse": ["緩弱", "沉遲"], "excluded": ["潮熱", "譫語"],
     "method": "溫法", "method_label": "溫中散寒、健脾"},
    {"pathogenesis": "少陰陽虛寒化", "channel": "少陰病",
     "required": ["但欲寐", "下利清穀", "手足厥冷", "惡寒踡臥"],
     "supporting": ["下利", "小便色白", "無熱惡寒", "吐利"],
     "pulse": ["微細", "沉微", "微欲絕"], "excluded": ["心煩不得眠", "渴欲飲水"],
     "method": "救逆", "method_label": "回陽救逆"},
    {"pathogenesis": "少陰陰虛熱化", "channel": "少陰病",
     "required": ["心煩", "不得臥", "不得眠"],
     "supporting": ["咽乾", "口燥", "咽痛"],
     "pulse": ["細數"], "excluded": ["下利清穀", "手足厥冷"],
     "method": "清法", "method_label": "滋陰清熱、交通心腎"},
    {"pathogenesis": "血虛寒凝（厥）", "channel": "厥陰病",
     "required": ["手足厥寒", "手足厥冷"],
     "supporting": ["惡寒"],
     "pulse": ["細欲絕", "微細"], "excluded": ["煩躁", "大渴"],
     "method": "溫法", "method_label": "養血散寒、溫通經脈"},
    {"pathogenesis": "上熱下寒（蛔厥）", "channel": "厥陰病",
     "required": ["吐蚘", "蛔厥"],
     "supporting": ["心中疼熱", "飢而不欲食", "煩躁"],
     "pulse": [], "excluded": [],
     "method": "和法", "method_label": "寒溫並用、安蛔止痛"},
    {"pathogenesis": "熱迫大腸（協熱利）", "channel": "陽明病",
     "required": ["熱利下重", "便膿血"],
     "supporting": ["下利", "渴欲飲水", "肛門灼熱"],
     "pulse": ["數"], "excluded": ["下利清穀"],
     "method": "清法", "method_label": "清熱燥濕止利"},
    {"pathogenesis": "瘀熱互結（蓄血）", "channel": "太陽病",
     "required": ["其人如狂", "少腹急結", "少腹硬滿"],
     "supporting": ["發狂", "善忘", "小便自利"],
     "pulse": ["沉澀"], "excluded": ["小便不利"],
     "method": "下法", "method_label": "破血逐瘀"},
    {"pathogenesis": "心陽不足（心悸）", "channel": "太陽病",
     "required": ["心下悸", "心動悸", "叉手自冒心"],
     "supporting": ["欲得按", "驚狂", "煩躁"],
     "pulse": ["結代"], "excluded": [],
     "method": "溫法", "method_label": "溫通心陽、鎮驚安神"},
    {"pathogenesis": "氣血兩虛（脈結代）", "channel": "太陽病",
     "required": ["心動悸"], "supporting": ["虛羸", "少氣"],
     "pulse": ["結代"], "excluded": [],
     "method": "補法", "method_label": "益氣滋陰、通陽復脈"},
]

# 方證關係分級：宋本原文標記 → 等級（可數的事實，非模型判斷）
RELATION_GRADES = {
    "主之": ("直接方證（某方主之）", "A"),
    "宜": ("方症證據（宜某方）", "B"),
    "屬": ("方症證據（屬某方證）", "B"),
    "與": ("試用性方證（與某方）", "B-"),
    "可與": ("試用性方證（可與某方）", "B-"),
}
_STRENGTH_ORDER = ["主之", "宜", "屬", "與", "可與"]

TONGUE_NOTE = ("宋本《傷寒論》無系統舌診主證（舌診體系成熟於後世），"
               "本引擎不設舌象維度——誠實缺位，不虛構知識。")

# 多維評分權重（透明常數；分項全部隨結果返回，可覆核）
WEIGHTS = {"symptom": 0.35, "pathogenesis": 0.15, "method": 0.15,
           "pulse": 0.10, "evidence": 0.25, "contraindication_penalty": 0.25}
_GRADE_SCORE = {"A": 1.0, "B": 0.75, "B-": 0.6, "D": 0.4}


# ═══════════════════════════════════════════════════════════════════
class CorrespondenceEngine:
    def __init__(self, registry):
        self.reg = getattr(registry, "_base", registry)
        self._strength_cache: Optional[Dict[str, Dict]] = None

    # -- 原文標記 → 方證關係分級 ------------------------------------------
    def _strengths(self) -> Dict[str, Dict]:
        if self._strength_cache is None:
            agg: Dict[str, Dict] = {}
            for r in read_jsonl(config.RULES_INITIAL_DIR / "initial_rules.jsonl"):
                if r["rule_type"] != "formula_pattern_rule":
                    continue
                s = r.get("prescription_strength", "")
                if s not in RELATION_GRADES:
                    continue
                for f in r.get("then_conclusions", {}).get("formula", []):
                    e = agg.setdefault(f, {"markers": {}, "examples": {}})
                    e["markers"][s] = e["markers"].get(s, 0) + 1
                    e["examples"].setdefault(s, r["clause_id"])
            self._strength_cache = agg
        return self._strength_cache

    def relation_grade(self, formula: str) -> Dict:
        e = self._strengths().get(formula)
        if not e:
            return {"relation": "類方/歸納方證（無原文處方標記）", "grade": "D",
                    "markers": {}, "example_clauses": {},
                    "basis": "規則庫歸納，未見宋本處方語式"}
        strongest = next(s for s in _STRENGTH_ORDER if s in e["markers"])
        relation, grade = RELATION_GRADES[strongest]
        return {"relation": relation, "grade": grade,
                "markers": e["markers"], "example_clauses": e["examples"],
                "basis": f"宋本處方語式標記（最強:{strongest}×{e['markers'][strongest]}）"}

    # -- 病機推理（D/E 層，透明依據） -------------------------------------
    @staticmethod
    def infer_pathogenesis(findings: List[str]) -> List[Dict]:
        present = {normalize_query(f) for f in findings if f.strip()}

        def hit(term_list):
            return [t for t in term_list
                    if any(t == p or t in p or p in t for p in present)]

        out = []
        for entry in PATHOGENESIS_MAP:
            req = hit(entry["required"])
            sup = hit(entry["supporting"])
            pul = hit(entry["pulse"])
            exc = hit(entry["excluded"])
            if not req and len(sup) + len(pul) < 2:
                continue
            # 軟飽和評分：證據越多分越高、與條目詞表大小無關（避免小條目
            # 憑歸一化佔便宜）；required 每中一項權重最高
            raw = (1.2 * min(len(req), 3) + 0.6 * min(len(sup), 4)
                   + (0.6 if pul else 0.0))
            score = raw / (raw + 1.5)
            if exc:
                score *= 0.25          # 排除證出現 → 強降權（不直接抹零，供覆核）
            out.append({
                "pathogenesis": entry["pathogenesis"],
                "channel": entry["channel"],
                "method": entry["method"],
                "method_label": entry["method_label"],
                "confidence": round(min(1.0, score), 2),
                "matched": {"required": req, "supporting": sup, "pulse": pul},
                "missing": [t for t in entry["required"] if t not in req][:3],
                "excluded_present": exc,
                "layer": "D/E 後世病機歸納",
            })
        out.sort(key=lambda x: -x["confidence"])
        return out[:4]

    # -- 方證畫像 ----------------------------------------------------------
    def profile(self, formula: str) -> Dict:
        name = lexicon.canonical_formula(normalize_query(formula))
        rule = next((r for r in self.reg.art.formula_rules
                     if r.formula == name), None)
        if rule is None:
            return {"error": f"未找到 {name} 的方證規則"}
        pattern = rule.core_symptoms + rule.associated_symptoms
        excluded = sorted({b for a, b in lexicon.CONTRADICTORY_SYMPTOMS
                           if a in pattern}
                          | {a for a, b in lexicon.CONTRADICTORY_SYMPTOMS
                             if b in pattern})
        methods = [t.therapy_method for t in self.reg.art.therapy_rules
                   if t.polarity == "indicated"
                   and name in t.representative_formulas]
        patho = [e["pathogenesis"] for e in PATHOGENESIS_MAP
                 if any(t in pattern for t in e["required"])          # 必備證命中
                 and len([t for t in (e["required"] + e["supporting"])
                          if t in pattern]) >= 2
                 and (not rule.six_channel_scope
                      or e["channel"] in rule.six_channel_scope)      # 六經一致
                 and not any(x in rule.core_symptoms for x in e["excluded"])]
        fam = lexicon.formula_family(name)
        family_members = [r.formula for r in self.reg.art.formula_rules
                          if r.formula != name
                          and lexicon.formula_family(r.formula) == fam] \
            if fam else []
        diff_partners = sorted({f for d in self.reg.art.differential_rules
                                if name in d.formulas for f in d.formulas
                                if f != name})
        similar = list(dict.fromkeys(family_members + diff_partners))  # 同族優先
        return {
            "formula": name,
            "relation": self.relation_grade(name),
            "core_symptoms": rule.core_symptoms,
            "optional_symptoms": rule.associated_symptoms,
            "core_pulse": rule.core_pulse,
            "excluded_patterns": excluded,        # 見則不宜（互斥證對推導）
            "pathogenesis_candidates": patho[:3],
            "pathogenesis_note": PATHOGENESIS_NOTE,
            "methods": methods,
            "contraindications": rule.contraindications[:3],
            "supporting_clauses": rule.supporting_clauses[:6],
            "similar_formulas": similar[:5],
            "family": fam,
            "tongue_note": TONGUE_NOTE,
        }

    # -- 主流程：8 段式方證對應 -------------------------------------------
    def analyze(self, symptoms: List[str], pulse: Optional[List[str]] = None,
                six_channel: Optional[str] = None,
                modern: Optional[str] = None, top_k: int = 4) -> Dict:
        symptoms = [normalize_query(s) for s in (symptoms or []) if s.strip()]
        pulse = [normalize_query(p) for p in (pulse or []) if p.strip()]

        # 1/2 — 問題解析 + 現代映射（可選）
        mapping = None
        if modern:
            from ..phenotype_map import map_modern
            mapping = map_modern(modern)
            if mapping and not symptoms:
                # 現代疾病無症狀輸入時，以映射的古籍詞作檢索性線索（顯式標注）
                symptoms = [normalize_query(t)
                            for t in mapping["classical_terms"][:4]]
        findings = symptoms + [p.lstrip("脈") for p in pulse]

        # 3 — 病機結構（D/E）
        syndromes = self.infer_pathogenesis(findings)
        methods = list(dict.fromkeys(
            s["method"] for s in syndromes[:2]))

        # 4/5 — 候選方 + 多維評分（透明分解）
        match = self.reg.matcher.match(symptoms=symptoms, pulse=pulse,
                                       six_channel=six_channel,
                                       top_k=max(top_k, 3))
        candidates = []
        for m in match.get("matched_formula_patterns", [])[:top_k]:
            prof = self.profile(m["formula"])
            grade = prof.get("relation", {})
            patho_hit = [p for p in prof.get("pathogenesis_candidates", [])
                         if any(p == s["pathogenesis"] for s in syndromes[:2])]
            method_hit = [mm for mm in prof.get("methods", []) if mm in methods]
            pulse_hits = [h for h in m.get("matched_findings", []) if "脈" in h]
            excluded_present = [x for x in prof.get("excluded_patterns", [])
                                if x in findings]
            dims = {
                "symptom": round(m.get("match_score", 0.0), 2),
                "pathogenesis": 1.0 if patho_hit else 0.0,
                "method": 1.0 if method_hit else 0.0,
                "pulse": min(1.0, len(pulse_hits) / max(len(pulse), 1))
                         if pulse else 0.0,
                "evidence": _GRADE_SCORE.get(grade.get("grade", "D"), 0.4),
                "contraindication_penalty": min(
                    1.0, 0.5 * len(m.get("conflicts", []))
                    + 0.5 * len(excluded_present)),
            }
            total = sum(WEIGHTS[k] * dims[k] for k in
                        ("symptom", "pathogenesis", "method", "pulse",
                         "evidence")) \
                - WEIGHTS["contraindication_penalty"] * dims["contraindication_penalty"]
            candidates.append({
                "formula": m["formula"],
                "total_score": round(max(0.0, total), 3),
                "score_breakdown": dims,
                "weights": WEIGHTS,
                "relation": grade,
                "matched_pathogenesis": patho_hit,
                "matched_methods": method_hit,
                "matched_findings": m.get("matched_findings", [])[:6],
                "conflicts": m.get("conflicts", []),
                "excluded_patterns_present": excluded_present,
                "evidence_clauses": [e["clause_id"]
                                     for e in m.get("evidence", [])][:4],
                "similar_formulas": prof.get("similar_formulas", [])[:3],
            })
        candidates.sort(key=lambda c: -c["total_score"])

        # 6 — 類方鑒別（top-2 對比 + 追問）
        differential = None
        questions: List[str] = []
        if len(candidates) >= 2:
            pair = [candidates[0]["formula"], candidates[1]["formula"]]
            d = self.reg.call("shanghan_differential", {"formulas": pair}) \
                if hasattr(self.reg, "call") else {}
            differential = {"pair": pair,
                            "key_discriminators":
                                (d.get("differential") or {})
                                .get("key_discriminators", [])[:4],
                            "supporting_clauses":
                                (d.get("differential") or {})
                                .get("supporting_clauses", [])[:5]}
            try:
                from ..agent.hypothesis import HypothesisManager
                hyp = HypothesisManager(self.reg).analyze(symptoms, pulse,
                                                          six_channel)
                questions = hyp.get("clarifying_questions", [])[:4]
            except Exception:
                pass

        # 7/8 — 證據鏈 + 邊界
        evidence_ids = list(dict.fromkeys(
            cid for c in candidates for cid in c["evidence_clauses"]))
        coverage_note = ""
        if mapping and not candidates:
            coverage_note = (
                "誠實邊界：宋本《傷寒論》方證規則庫未覆蓋該現代表型的直接"
                "方證（腎氣丸/六味地黃丸等屬後世方，超出宋本結構化範圍）。"
                "建議調 shanghan_omni_search（include_library=true）檢索"
                "800+ 部後世方書的段落級旁證。")
        return {
            "tool": "shanghan_correspondence",
            "query_analysis": {"symptoms": symptoms, "pulse": pulse,
                               "six_channel": six_channel, "modern": modern},
            "modern_mapping": mapping,
            "candidate_syndromes": syndromes,
            "syndrome_note": PATHOGENESIS_NOTE,
            "derived_methods": methods,
            "candidate_formulas": candidates,
            "differential": differential,
            "clarifying_questions": questions,
            "evidence_clause_ids": evidence_ids,
            "coverage_note": coverage_note,
            "tongue_note": TONGUE_NOTE,
            "safety_boundary": ("僅用於古籍知識發現與方證研究，不作為處方建議；"
                                "方證關係分級由宋本處方語式推導，病機/治法屬"
                                "後世歸納（D/E層）。"),
        }
