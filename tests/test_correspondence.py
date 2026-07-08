"""方證對應引擎測試：關係分級（原文標記推導）、病機推理（透明依據+軟飽和
評分）、方證畫像（排除證/六經約束）、多維評分分解、類方鑒別、現代疾病入口
誠實邊界、路由與患者隔離."""
import unittest

from hermes_shanghan import config


def _ensure_artifacts():
    if not (config.RULES_INITIAL_DIR / "initial_rules.jsonl").exists():
        from hermes_shanghan.orchestrator import run_pipeline
        run_pipeline(verbose=False)


def _engine():
    from hermes_shanghan.agent.tools import get_registry
    from hermes_shanghan.induce.correspondence import CorrespondenceEngine
    return CorrespondenceEngine(get_registry())


class TestRelationGrade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        cls.eng = _engine()

    def test_zhuzhi_marker_gives_grade_a(self):
        g = self.eng.relation_grade("桂枝湯")
        self.assertEqual(g["grade"], "A")
        self.assertIn("主之", g["markers"])
        self.assertGreaterEqual(g["markers"]["主之"], 2)
        # 分級依據可回源到具體條文
        self.assertTrue(g["example_clauses"]["主之"].startswith("SHL_SONGBEN"))

    def test_unknown_formula_grades_d(self):
        g = self.eng.relation_grade("不存在方")
        self.assertEqual(g["grade"], "D")


class TestPathogenesisInference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        cls.eng = _engine()

    def test_taiyang_zhongfeng(self):
        out = self.eng.infer_pathogenesis(["發熱", "汗出", "惡風", "浮緩"])
        top = out[0]
        self.assertEqual(top["pathogenesis"], "營衛不和（表虛）")
        self.assertIn("汗出", top["matched"]["required"])
        self.assertIn("D/E", top["layer"])          # 誠實標層

    def test_shaoyin_hanhua_beats_smaller_entry(self):
        # 軟飽和評分：證據多者勝，與條目詞表大小無關
        out = self.eng.infer_pathogenesis(
            ["但欲寐", "下利清穀", "手足厥冷", "微細"])
        self.assertEqual(out[0]["pathogenesis"], "少陰陽虛寒化")

    def test_excluded_symptom_downweights(self):
        with_ex = self.eng.infer_pathogenesis(["汗出", "惡風", "無汗"])
        entry = next(e for e in with_ex
                     if e["pathogenesis"] == "營衛不和（表虛）")
        self.assertIn("無汗", entry["excluded_present"])
        self.assertLess(entry["confidence"], 0.4)   # 強降權


class TestFormulaProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        cls.eng = _engine()

    def test_guizhi_profile(self):
        p = self.eng.profile("桂枝湯")
        self.assertIn("無汗", p["excluded_patterns"])      # 互斥證對推導
        self.assertEqual(p["pathogenesis_candidates"], ["營衛不和（表虛）"])
        self.assertIn("汗法", p["methods"])
        self.assertEqual(p["relation"]["grade"], "A")
        self.assertIn("舌診", p["tongue_note"])            # 誠實缺位聲明
        # 類方同族優先
        self.assertTrue(any("桂枝" in f for f in p["similar_formulas"][:3]))


class TestCorrespondenceAnalyze(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        cls.eng = _engine()

    def test_eight_part_output_guizhi(self):
        out = self.eng.analyze(["發熱", "汗出", "惡風"], pulse=["脈浮緩"])
        top = out["candidate_formulas"][0]
        self.assertEqual(top["formula"], "桂枝湯")
        # 多維評分透明分解 + 權重可見
        for dim in ("symptom", "pathogenesis", "method", "pulse",
                    "evidence", "contraindication_penalty"):
            self.assertIn(dim, top["score_breakdown"])
        self.assertIn("weights", top)
        self.assertEqual(top["relation"]["grade"], "A")
        # 類方鑒別 + 追問 + 邊界
        self.assertTrue(out["differential"]["pair"])
        self.assertTrue(out["clarifying_questions"])
        self.assertIn("不作為處方建議", out["safety_boundary"])
        self.assertTrue(out["evidence_clause_ids"])

    def test_contraindication_penalty_applies(self):
        # 無汗是桂枝湯排除證：桂枝湯要麼被罰分要麼不再居首
        out = self.eng.analyze(["發熱", "惡風", "無汗"])
        gz = next((c for c in out["candidate_formulas"]
                   if c["formula"] == "桂枝湯"), None)
        if gz is not None:
            self.assertTrue(
                gz["score_breakdown"]["contraindication_penalty"] > 0
                or out["candidate_formulas"][0]["formula"] != "桂枝湯")

    def test_modern_entry_honest_boundary(self):
        out = self.eng.analyze([], modern="骨質疏鬆")
        self.assertEqual(out["modern_mapping"]["modern"], "骨質疏鬆")
        # 宋本不含腎氣丸類——無候選時給誠實邊界而非硬湊
        if not out["candidate_formulas"]:
            self.assertIn("誠實邊界", out["coverage_note"])
            self.assertIn("omni_search", out["coverage_note"])

    def test_shaoyang_full_dims(self):
        out = self.eng.analyze(["往來寒熱", "胸脅苦滿", "口苦"])
        self.assertEqual(out["candidate_syndromes"][0]["pathogenesis"],
                         "少陽樞機不利")
        top = out["candidate_formulas"][0]
        self.assertEqual(top["formula"], "小柴胡湯")
        self.assertEqual(top["score_breakdown"]["pathogenesis"], 1.0)
        self.assertEqual(top["score_breakdown"]["method"], 1.0)


class TestToolRoutingIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_tool_registered_and_isolated(self):
        from hermes_shanghan.agent.tools import get_registry
        reg = get_registry()
        self.assertIn("shanghan_correspondence", reg.names())
        out = reg.call("shanghan_correspondence",
                       {"symptoms": ["往來寒熱", "口苦"]})
        self.assertTrue(out["candidate_formulas"])
        self.assertNotIn("shanghan_correspondence",
                         reg.for_role("patient").names())
        # 無症狀無現代病名 → 明確報錯
        out = reg.call("shanghan_correspondence", {})
        self.assertIn("error", out)

    def test_local_routing(self):
        from hermes_shanghan.agent.agent import ShanghanAgent
        out = ShanghanAgent().ask(
            "病人發熱汗出惡風脈浮緩，請做方證對應辨證分析，屬何證？",
            role="doctor")
        self.assertEqual(out["tools_used"][0], "shanghan_correspondence")
        self.assertIn("方證對應分析", out["answer"])
        self.assertIn("A級", out["answer"])
        self.assertTrue(out["citation_report"]["ok"])

    def test_match_routing_not_hijacked(self):
        from hermes_shanghan.agent.agent import ShanghanAgent
        out = ShanghanAgent().ask("病人發熱惡風汗出脈緩，考慮什麼方？",
                                  role="doctor")
        self.assertEqual(out["tools_used"][0], "shanghan_match_formula")


if __name__ == "__main__":
    unittest.main()
