"""多觀點論證引擎 — 不消滅分歧，而是結構化分歧.

回應「條文標籤化」批判的工程化方案：同一條文/方證，由七個**解釋範式**
各自生成結構化觀點節點（claim + 證據 + 推理路徑 + 適用範圍 + 侷限 +
證據層級 + 強度），爭議仲裁器提取共同點/分歧點/場景指引——
**不裁決真理，只給證據強度**。

本庫的獨特優勢：學派分歧不靠人工杜撰觀點庫，而錨定真實數據——
九部注本對齊層（C 層）給出每條的注家數、術語分歧度與各家特徵術語
（如第12條：7 家注、分歧度 0.92，成無己重「榮衛/腠理」、柯琴重
「寒熱/胃氣」、尤怡重「邪氣」）——歷史分歧本身是可數的。

七範式與證據層級：
  條文字面(A) · 六經辨證(D錨A提綱) · 方證對應(A-D,處方語式分級) ·
  病機醫理(D/E,推斷顯式標注) · 藥證藥組(D/E) · 類方鑒別(D) ·
  注家歷史觀點(C,真實注文)
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from .. import config
from ..textutil import normalize_query

# ═══════════════════════════════════════════════════════════════════
# 隱含醫理提示表（D/E 層）：症狀 → 機理線索——「汗出」不能只解釋為
# 「有汗」，但每條提示都明確是後世醫理框架，非條文明示
# ═══════════════════════════════════════════════════════════════════
SYMPTOM_MECHANISM: Dict[str, str] = {
    "汗出": "營陰外泄、衛外不固", "自汗出": "表虛營弱、衛不外固",
    "無汗": "寒邪束表、腠理閉塞", "惡風": "衛陽不固、肌表失護",
    "惡寒": "寒邪外束或陽氣不足", "發熱": "正邪相爭、陽氣鬱遏",
    "往來寒熱": "正邪分爭於半表半裏", "胸脅苦滿": "少陽經氣不利、樞機不暢",
    "口苦": "膽熱上蒸", "咽乾": "熱傷津液", "目眩": "清陽被擾",
    "身疼痛": "寒凝經脈、營衛滯澀", "頭項強痛": "太陽經氣不舒",
    "但欲寐": "陽氣衰微、陰寒內盛", "下利清穀": "脾腎陽衰、火不腐熟",
    "手足厥冷": "陽氣不達四末", "心下痞": "中焦氣機痞塞、升降失常",
    "煩躁": "陽鬱化熱、擾動心神", "心煩": "熱擾胸膈",
    "小便不利": "膀胱氣化不行、水津不布", "渴欲飲水": "津液不布或熱盛傷津",
    "譫語": "熱擾神明", "心下悸": "水氣凌心或心陽不足",
    "喘": "肺氣上逆、宣降失司", "嘔": "胃氣上逆",
    "腹滿": "中焦壅滯", "不大便": "腑氣不通、燥屎內結",
    "脈浮": "病位在表", "脈緩": "非寒邪緊束、營衛尚和之象",
    "脈緊": "寒邪收引", "脈微細": "陽氣衰微、陰血不足",
    "脈弦": "少陽氣鬱", "脈結代": "心之氣血不繼",
}
MECHANISM_NOTE = "機理提示屬後世醫理框架（D/E 層推斷），非條文逐字明示"

# 解釋範式登記表：key → (名稱, 關注點, 適合任務)
PARADIGMS = {
    "literal": ("條文字面", "原文症狀/方名/處方語式", "原文考據、直接方證檢索"),
    "six_channel": ("六經辨證", "病位病性病程、與提綱互參", "六經定位、傳變分析"),
    "fangzheng": ("方證對應", "症狀組合↔方劑、處方語式分級", "方證匹配、教學"),
    "bingji": ("病機醫理", "寒熱虛實、營衛氣血、氣機", "深層解釋（須標推斷）"),
    "yaozheng": ("藥證藥組", "單藥角色、藥對結構", "方解、配伍解釋"),
    "leifang": ("類方鑒別", "相似方關鍵差異", "鑒別診斷、誤用防範"),
    "zhujia": ("注家歷史", "九注本真實注文與分歧度", "學術史、分歧研究"),
}

RE_MARKER = re.compile(r"(主之|宜[^。，]{0,8}湯|可與|不可與|屬[^。，]{0,6}湯)")


class PerspectiveCouncil:
    """七範式觀點生成 + 爭議仲裁（每個觀點必須引用結構化證據）。"""

    def __init__(self, registry):
        self.reg = getattr(registry, "_base", registry)
        self._div = None

    # ------------------------------------------------------------------
    def _divergence_row(self, clause_id: str) -> Optional[Dict]:
        if self._div is None:
            p = config.RESEARCH_DIR / "commentary_divergence.json"
            self._div = json.loads(p.read_text(encoding="utf-8")) \
                if p.exists() else {"clauses": []}
        return next((r for r in self._div["clauses"]
                     if r["clause_id"] == clause_id), None)

    # ------------------------------------------------------------------
    def deliberate(self, ref: Optional[str] = None,
                   formula: Optional[str] = None) -> Dict:
        """入口：條文號/clause_id 或 方名，生成多觀點論證。"""
        clause = None
        if ref:
            clause = self.reg.clause_rag.get_clause(str(ref).strip())
            if clause is None:
                return {"error": f"未找到條文 {ref}"}
            if not formula and clause.formula_names:
                formula = clause.formula_names[0]
        rule = None
        if formula:
            from .. import lexicon
            formula = lexicon.canonical_formula(normalize_query(formula))
            rule = next((r for r in self.reg.art.formula_rules
                         if r.formula == formula), None)
            if clause is None and rule and rule.supporting_clauses:
                clause = self.reg.art.clause_store().get(
                    rule.supporting_clauses[0])
        if clause is None and rule is None:
            return {"error": "請提供條文號（ref）或方名（formula）"}

        positions: List[Dict] = []
        for builder in (self._p_literal, self._p_six_channel,
                        self._p_fangzheng, self._p_bingji,
                        self._p_yaozheng, self._p_leifang, self._p_zhujia):
            pos = builder(clause, formula, rule)
            if pos:
                positions.append(pos)
        adjudication = self._adjudicate(positions, clause)
        return {
            "tool": "shanghan_perspectives",
            "target": {"clause_id": clause.clause_id if clause else None,
                       "clause_number": getattr(clause, "clause_number", None)
                       if clause else None,
                       "formula": formula},
            "positions": positions,
            "adjudication": adjudication,
            "evidence_grading_note": (
                "各觀點標注證據層級：A 原文直述／C 注家歷史注文／"
                "D 後世歸納／D/E 醫理推斷——推斷絕不冒充原文明示。"),
            "boundary": ("多觀點論證用於古籍深度理解與分歧研究；"
                         "各範式適用場景見 scenario_guide，不構成臨床處方依據。"),
        }

    # ══ 七範式觀點生成器（無數據則返回 None，絕不硬湊） ══════════════
    def _p_literal(self, clause, formula, rule) -> Optional[Dict]:
        if clause is None:
            return None
        marker = RE_MARKER.search(clause.clean_text)
        findings = list(clause.symptoms) + list(clause.pulse)
        return self._position(
            "literal",
            claim=(f"本條字面：{'、'.join(findings[:6]) or '（無症狀詞）'}"
                   + (f"，處方語式「{marker.group(1)}」" if marker else "")
                   + (f"，方為{formula}" if formula else "")),
            evidence=[clause.clause_id],
            reasoning=[f"原文：「{clause.clean_text[:60]}…」"
                       if len(clause.clean_text) > 60
                       else f"原文：「{clause.clean_text}」"],
            scope="原文考據——只陳述條文寫了什麼，不作延伸",
            limitation="未明說病機；孤立看單條易失上下文",
            layer="A")

    def _p_six_channel(self, clause, formula, rule) -> Optional[Dict]:
        channel = (clause.six_channel if clause else None) or \
            (rule.six_channel_scope[0] if rule and rule.six_channel_scope
             else None)
        if not channel:
            return None
        scr = next((r for r in self.reg.art.six_channel_rules
                    if r.six_channel == channel), None)
        if scr is None:
            return None
        return self._position(
            "six_channel",
            claim=f"六經定位：{channel}——{scr.summary[:40]}",
            evidence=[scr.outline_clause_id]
                     + ([clause.clause_id] if clause else []),
            reasoning=[f"提綱互參：「{scr.outline_text[:36]}」"
                       f"（{scr.outline_clause_id}）"],
            scope="病位病性定位、傳變分析",
            limitation="六經本質歷代有經絡/病位/階段諸說，此為篇章歸納",
            layer="D（錨定 A 層提綱條文）")

    def _p_fangzheng(self, clause, formula, rule) -> Optional[Dict]:
        if rule is None:
            return None
        from ..induce.correspondence import CorrespondenceEngine
        grade = CorrespondenceEngine(self.reg).relation_grade(rule.formula)
        return self._position(
            "fangzheng",
            claim=(f"{rule.formula}方證：核心證組合「"
                   f"{'、'.join(rule.core_symptoms[:4])}」；"
                   f"關係分級 {grade['grade']}（{grade['relation']}）"),
            evidence=rule.supporting_clauses[:4],
            reasoning=[f"分級依據：{grade['basis']}",
                       f"核心脈：{'、'.join(rule.core_pulse[:3]) or '—'}"],
            scope="方證匹配、類方教學",
            limitation="重症狀組合，對體質/雜病延伸解釋不足",
            layer=grade["grade"])

    def _p_bingji(self, clause, formula, rule) -> Optional[Dict]:
        findings = (list(clause.symptoms) + list(clause.pulse)) if clause \
            else (rule.core_symptoms if rule else [])
        if not findings:
            return None
        from ..induce.correspondence import CorrespondenceEngine
        syndromes = CorrespondenceEngine.infer_pathogenesis(findings)
        if not syndromes:
            return None
        top = syndromes[0]
        chain = []
        for f in findings:
            hit = SYMPTOM_MECHANISM.get(f) or next(
                (v for k, v in SYMPTOM_MECHANISM.items() if k in f), None)
            if hit and len(chain) < 5:
                chain.append(f"{f}→{hit}")
        return self._position(
            "bingji",
            claim=(f"隱含病機推斷：{top['pathogenesis']}"
                   f"（信度 {top['confidence']}）——{MECHANISM_NOTE}"),
            evidence=([clause.clause_id] if clause else [])
                     or rule.supporting_clauses[:2],
            reasoning=chain or [f"依據症狀組合 {'、'.join(findings[:4])}"],
            scope="深層醫理解釋、病機教學（顯式標注推斷）",
            limitation="病機術語屬後世框架；方證派或弱化之，醫理派或強調之"
                       "——本身即是學派分歧點",
            layer="D/E（推斷）")

    def _p_yaozheng(self, clause, formula, rule) -> Optional[Dict]:
        if not formula:
            return None
        try:
            card = self.reg.pharma["formula"].explain(formula)
        except Exception:
            return None
        if card.get("error"):
            return None
        roles = card["roles"]["assignments"][:4]
        pair = (card.get("pairing") or [{}])[0]
        role_txt = "；".join(f"{a['herb']}={a['role']}" for a in roles)
        return self._position(
            "yaozheng",
            claim=f"藥證結構：{role_txt}",
            evidence=[card["evidence_trace"]["block_clause_id"]],
            reasoning=[f"{a['herb']}：{a['basis']}" for a in roles[:3]]
                      + ([f"高頻藥對 {'×'.join(pair.get('pair', []))}"
                          f"（同見 {pair.get('n_formulas_together')} 方）"]
                         if pair.get("pair") else []),
            scope="方解、配伍規律",
            limitation=card["roles"]["layer"],
            layer="D/E（角色推導透明）")

    def _p_leifang(self, clause, formula, rule) -> Optional[Dict]:
        if rule is None:
            return None
        partner = next((d for d in self.reg.art.differential_rules
                        if rule.formula in d.formulas), None)
        if partner is None:
            return None
        others = [f for f in partner.formulas if f != rule.formula]
        return self._position(
            "leifang",
            claim=(f"類方視角：須與{'、'.join(others)}鑒別——"
                   + "；".join(partner.key_discriminators[:2])),
            evidence=partner.supporting_clauses[:4],
            reasoning=partner.key_discriminators[:4],
            scope="鑒別診斷、誤用防範（回答「為什麼不是另一個方」）",
            limitation="鑒別軸為跨條歸納（D層）",
            layer="D")

    def _p_zhujia(self, clause, formula, rule) -> Optional[Dict]:
        if clause is None:
            return None
        row = self._divergence_row(clause.clause_id)
        if not row:
            return None
        excerpts = []
        for c in self.reg.art.commentary_rules:
            if c.clause_id == clause.clause_id and len(excerpts) < 3:
                excerpts.append(f"{c.commentator}《{c.book}》："
                                f"{c.commentary_text[:40]}…")
        distinctive = "；".join(f"{k}重「{'、'.join(v[:2])}」"
                                for k, v in
                                list(row.get("distinctive_terms", {}).items())[:3])
        level = "高" if row["term_divergence"] >= 0.7 else \
                ("中" if row["term_divergence"] >= 0.4 else "低")
        return self._position(
            "zhujia",
            claim=(f"注家歷史：{row['n_commentators']} 家注本條，"
                   f"術語分歧度 {row['term_divergence']}（{level}）——"
                   f"歷史上本就存在解釋分歧" + (f"：{distinctive}" if distinctive else "")),
            evidence=[clause.clause_id],
            reasoning=excerpts or ["（注文對齊記錄見分歧圖譜）"],
            scope="學術史、詮釋分歧研究",
            limitation="注文屬 C 層解釋，不改變 A 層原文",
            layer="C（真實注文，分歧度為對齊層計量）")

    # ------------------------------------------------------------------
    @staticmethod
    def _position(key, claim, evidence, reasoning, scope, limitation,
                  layer) -> Dict:
        name, focus, suits = PARADIGMS[key]
        strength = ("高" if layer.startswith(("A", "B")) else
                    "中" if layer.startswith(("C", "D（")) or layer == "D" else "低-中")
        return {"paradigm": name, "paradigm_key": key, "focus": focus,
                "claim": claim, "supporting_evidence": evidence,
                "reasoning_path": reasoning, "scope": scope,
                "limitation": limitation, "layer": layer,
                "strength": strength, "suits": suits}

    # ══ 爭議仲裁：共同點/分歧點/強度/場景——不裁決真理 ═══════════════
    def _adjudicate(self, positions: List[Dict], clause) -> Dict:
        by = {p["paradigm_key"]: p for p in positions}
        common: List[str] = []
        if "literal" in by and "six_channel" in by:
            common.append("六經定位與條文篇章一致（字面派與六經派互證）")
        if "literal" in by and "fangzheng" in by and \
                by["fangzheng"]["layer"] in ("A", "B"):
            common.append("主方對應有宋本處方語式直接支持（字面與方證派一致）")
        if "leifang" in by:
            common.append("各範式均承認須經類方鑒別，方證不由單一症狀決定")

        divergences: List[str] = []
        if "bingji" in by:
            divergences.append("病機層是主要分歧點：醫理派以之為核心解釋，"
                               "方證派視為推斷附註——本引擎標 D/E，兩種用法並存")
        if "zhujia" in by:
            divergences.append(by["zhujia"]["claim"])
        if "yaozheng" in by:
            divergences.append("君臣佐使為後世方論框架推導，非原文明文"
                               "（藥證派內部對角色劃分亦有出入）")

        strength_table = [{"paradigm": p["paradigm"], "layer": p["layer"],
                           "strength": p["strength"],
                           "n_evidence": len(p["supporting_evidence"])}
                          for p in positions]
        scenario_guide = [f"{p['paradigm']}：適合{p['suits']}"
                          for p in positions]
        return {"common_ground": common,
                "divergences": divergences,
                "strength_table": strength_table,
                "scenario_guide": scenario_guide,
                "note": "仲裁不裁決唯一正解，只給證據層級與適用場景——"
                        "分歧本身是被建模的知識對象"}
