"""多觀點論證引擎測試：七解釋範式並立、觀點節點結構（claim/證據/論證路徑/
適用範圍/侷限）、注家範式錨定真實分歧數據、D/E 推斷標注（機理不冒充原文）、
爭議仲裁（結構化分歧不裁決）、方名入口、錯誤處理、路由與患者隔離."""
import unittest

from hermes_shanghan import config


def _ensure_artifacts():
    if not (config.RESEARCH_DIR / "commentary_divergence.json").exists():
        from hermes_shanghan.orchestrator import run_pipeline
        run_pipeline(verbose=False)


class TestPerspectiveCouncil(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        from hermes_shanghan.agent.tools import get_registry
        cls.reg = get_registry()
        cls.out = cls.reg.call("shanghan_perspectives", {"ref": "12"})

    def test_seven_paradigms_all_present_for_clause_12(self):
        keys = [p["paradigm_key"] for p in self.out["positions"]]
        self.assertEqual(keys, ["literal", "six_channel", "fangzheng",
                                "bingji", "yaozheng", "leifang", "zhujia"])
        self.assertEqual(self.out["target"]["clause_id"], "SHL_SONGBEN_0012")
        self.assertEqual(self.out["target"]["formula"], "桂枝湯")

    def test_position_node_structure(self):
        # 觀點節點 = claim + evidence + reasoning_path + scope + limitation
        for p in self.out["positions"]:
            for field in ("paradigm", "claim", "supporting_evidence",
                          "reasoning_path", "scope", "limitation",
                          "layer", "strength", "suits"):
                self.assertIn(field, p)
            self.assertTrue(p["claim"])
            self.assertTrue(p["supporting_evidence"],
                            msg=f"{p['paradigm']} 無證據鏈不成觀點")

    def test_literal_position_is_layer_a_with_clause_evidence(self):
        lit = next(p for p in self.out["positions"]
                   if p["paradigm_key"] == "literal")
        self.assertEqual(lit["layer"], "A")
        self.assertIn("SHL_SONGBEN_0012", lit["supporting_evidence"])
        self.assertIn("主之", lit["claim"])

    def test_zhujia_anchors_real_divergence_data(self):
        # 注家範式必須錨定 commentary_divergence.json 的真實計量：
        # 第12條 7 家注、分歧度 0.9167，且論證路徑含真實注文摘錄
        zj = next(p for p in self.out["positions"]
                  if p["paradigm_key"] == "zhujia")
        self.assertIn("7 家注", zj["claim"])
        self.assertIn("0.9167", zj["claim"])
        self.assertIn("成無己", "".join(zj["reasoning_path"]))
        self.assertTrue(zj["layer"].startswith("C"))

    def test_mechanism_inference_labeled_not_disguised(self):
        # 隱含醫理補全：症狀→機理標 D/E 推斷，絕不冒充原文明示
        bj = next(p for p in self.out["positions"]
                  if p["paradigm_key"] == "bingji")
        self.assertIn("D/E", bj["layer"])
        self.assertIn("推斷", bj["claim"])
        self.assertTrue(any("→" in step for step in bj["reasoning_path"]))

    def test_adjudication_structures_divergence_without_verdict(self):
        adj = self.out["adjudication"]
        self.assertTrue(adj["common_ground"])
        self.assertTrue(adj["divergences"])
        self.assertEqual(len(adj["strength_table"]), 7)
        self.assertEqual(len(adj["scenario_guide"]), 7)
        self.assertIn("不裁決", adj["note"])
        # 真實歷史分歧進入分歧點而非被抹平
        self.assertTrue(any("0.9167" in d for d in adj["divergences"]))

    def test_formula_entry_resolves_to_anchor_clause(self):
        out = self.reg.call("shanghan_perspectives", {"formula": "桂枝湯"})
        self.assertEqual(out["target"]["formula"], "桂枝湯")
        self.assertTrue(out["target"]["clause_id"].startswith("SHL_SONGBEN"))
        self.assertEqual(len(out["positions"]), 7)

    def test_error_when_no_target(self):
        out = self.reg.call("shanghan_perspectives", {})
        self.assertIn("error", out)


class TestPerspectivesWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_routing_interpretation_vs_plain_lookup(self):
        # 「怎麼理解」問詮釋 → perspectives；「原文與規則」問文本 → get_clause；
        # 「注家…分歧」仍歸分歧圖譜——三路互不侵佔
        from hermes_shanghan.agent.agent import ShanghanAgent
        a = ShanghanAgent()
        out = a.ask("第12條怎麼理解？", role="researcher")
        self.assertIn("shanghan_perspectives", out["tools_used"])
        self.assertIn("多觀點論證", out["answer"])
        out = a.ask("第12條的原文與規則是什麼？", role="researcher")
        self.assertIn("shanghan_get_clause", out["tools_used"])
        out = a.ask("注家對第12條有何分歧？", role="researcher")
        self.assertIn("shanghan_divergence_atlas", out["tools_used"])

    def test_patient_role_excluded(self):
        # 學術論證工具不進患者面：patient 視圖不暴露 perspectives
        from hermes_shanghan.agent.tools import get_registry
        reg = get_registry()
        self.assertIn("shanghan_perspectives", reg.names())
        self.assertNotIn("shanghan_perspectives",
                         reg.for_role("patient").names())

    def test_webui_renderer(self):
        from hermes_shanghan.apps.webui import tool_perspectives
        html = tool_perspectives("12")
        self.assertEqual(html.count("hyp-card"), 7)
        self.assertIn("爭議仲裁", html)
        self.assertIn("⚠️", tool_perspectives("不存在的目標"))


if __name__ == "__main__":
    unittest.main()
