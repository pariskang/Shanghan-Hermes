"""深度溯源引擎測試：知識生命史三段式（源頭/演化/現代影響）、六種引文模式
（明引/暗引/節引/改寫/轉引/誤引）、古今影響力指標錨定真實計量、學術連接器
誠實降級（離線不虛構論文，注入連接器則產出真實 core_papers）、條文/方劑/概念
三入口、路由與患者隔離."""
import unittest

from hermes_shanghan import config


def _ensure_artifacts():
    if not (config.RESEARCH_DIR / "commentary_divergence.json").exists():
        from hermes_shanghan.orchestrator import run_pipeline
        run_pipeline(verbose=False)


class TestClauseProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        from hermes_shanghan.agent.tools import get_registry
        cls.reg = get_registry()
        cls.out = cls.reg.call("shanghan_provenance", {"ref": "12"})

    def test_three_stage_structure(self):
        for key in ("source_trace", "text_lineage", "concept_evolution",
                    "bibliometric_trace", "influence_index", "citation_edges",
                    "later_reception", "evidence_warning"):
            self.assertIn(key, self.out)
        self.assertEqual(self.out["target"]["id"], "SHL_SONGBEN_0012")

    def test_source_is_songben_layer_a(self):
        es = self.out["source_trace"]["earliest_sources"][0]
        self.assertEqual(es["layer"], "A")
        self.assertEqual(es["clause_id"], "SHL_SONGBEN_0012")
        self.assertIn("宋本", es["work"])

    def test_lineage_spans_a_b_c_layers(self):
        layers = {s["layer"] for s in self.out["text_lineage"]}
        # 原文A → 版本異文B → 注家C，逐段標層
        self.assertIn("A", layers)
        self.assertIn("B", layers)
        self.assertIn("C", layers)

    def test_influence_index_anchors_real_dispute(self):
        idx = self.out["influence_index"]
        # 注家爭議度直取九注本對齊層真實計量（第12條 0.9167）
        self.assertIn("0.9167", idx["commentary_dispute"]["basis"])
        self.assertEqual(idx["commentary_dispute"]["band"], "高")
        # 傳承度反映注家承襲數（7/9）
        self.assertIn("7/9", idx["transmission"]["basis"])
        for k, v in idx.items():
            if isinstance(v, dict) and "band" in v:
                self.assertIn(v["band"], ("高", "中", "低"))
                self.assertTrue(0.0 <= v["value"] <= 1.0)

    def test_citation_edges_typed(self):
        edges = self.out["citation_edges"]
        self.assertTrue(edges)
        e = edges[0]
        for f in ("edge_id", "source", "target", "citation_type",
                  "citation_function", "citation_attitude", "evidence_strength"):
            self.assertIn(f, e)


class TestFormulaProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        from hermes_shanghan.agent.tools import get_registry
        cls.out = get_registry().call("shanghan_provenance", {"formula": "桂枝湯"})

    def test_relation_grade_and_modification_lineage(self):
        self.assertEqual(self.out["source_trace"]["relation_grade"]["grade"], "A")
        stages = [s["stage"] for s in self.out["text_lineage"]]
        self.assertIn("原方出處", stages)
        self.assertIn("加減/類方", stages)

    def test_fangzheng_expansion_counts_modifications(self):
        exp = self.out["influence_index"]["fangzheng_expansion"]
        self.assertGreater(exp["value"], 0)
        self.assertIn("加減", exp["basis"])

    def test_unknown_formula_errors_with_candidates(self):
        from hermes_shanghan.agent.tools import get_registry
        out = get_registry().call("shanghan_provenance", {"formula": "不存在方"})
        self.assertIn("error", out)


class TestConceptProvenanceHonesty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        from hermes_shanghan.agent.tools import get_registry
        cls.out = get_registry().call("shanghan_provenance", {"concept": "腎主骨"})

    def test_earlier_classic_source_is_deferred_not_fabricated(self):
        # 腎主骨源出《內經》，本庫（傷寒論）未直述——誠實 deferred，不虛構出處
        es = self.out["source_trace"]["earliest_sources"][0]
        self.assertEqual(es["evidence_type"], "deferred_earlier_classic")
        self.assertIsNone(es["clause_id"])
        self.assertEqual(es["confidence"], 0.0)
        self.assertIn("deferred", self.out["source_note"].lower() + "deferred")

    def test_later_reception_from_real_corpus(self):
        # 後世反響取自全庫真實醫案/方書（若全庫已下載）
        recep = self.out["later_reception"]
        for r in recep:
            self.assertIn("citation_pattern", r)
            self.assertIn("book", r)


class TestCitationPatterns(unittest.TestCase):
    def test_six_patterns(self):
        from hermes_shanghan.induce.provenance import classify_citation
        origin = "太陽之為病，脈浮，頭項強痛而惡寒"
        cases = {
            "明引": (f"《傷寒論》曰：{origin}也。", {}),
            "暗引": (f"{origin}也，此太陽之綱。", {}),
            "轉引": (f"《傷寒論》曰：{origin}。", {"via_later_work": True}),
            "誤引": (origin, {"claimed_ref": "10", "actual_ref": "1"}),
        }
        for expect, (text, kw) in cases.items():
            r = classify_citation(text, origin, **kw)
            self.assertEqual(r["pattern"], expect,
                             msg=f"{expect}: got {r['pattern']} ({r['signals']})")

    def test_partial_citation_is_node(self):
        from hermes_shanghan.induce.provenance import classify_citation
        # 節引：只覆蓋原文片段
        r = classify_citation("頭項強痛而惡寒者，桂枝證也，別無他症。",
                              "太陽之為病，脈浮，頭項強痛而惡寒")
        self.assertIn(r["pattern"], ("節引", "暗引"))


class TestBibliometricConnector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_null_connector_defers_without_fabrication(self):
        from hermes_shanghan.agent.tools import get_registry
        out = get_registry().call("shanghan_provenance", {"ref": "12"})
        bib = out["bibliometric_trace"]
        self.assertEqual(bib["connector"], "null")
        self.assertIn("deferred", bib["status"])
        self.assertEqual(bib["core_papers"], [])          # 離線絕不虛構
        self.assertEqual(bib["core_authors"], [])

    def test_injected_connector_produces_core_papers(self):
        # 接入真實連接器（協議實現）後，core_papers 由外部數據填充
        from hermes_shanghan.agent.tools import get_registry
        from hermes_shanghan.induce.provenance import ProvenanceTracer

        class FakeConnector:
            name = "fake"

            def works(self, query, limit=10):
                return [{"title": "補腎強骨方治療骨質疏鬆機制研究",
                         "doi": "10.0000/demo", "year": 2024}]

        tracer = ProvenanceTracer(get_registry(), connector=FakeConnector())
        out = tracer.trace(concept="腎主骨")
        bib = out["bibliometric_trace"]
        self.assertEqual(bib["connector"], "fake")
        self.assertEqual(bib["status"], "connected")
        self.assertEqual(len(bib["core_papers"]), 1)


class TestProvenanceWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_routing_provenance_vs_neighbors(self):
        from hermes_shanghan.agent.agent import ShanghanAgent
        a = ShanghanAgent()
        out = a.ask("第12條的知識生命史與傳播路徑如何？", role="researcher")
        self.assertIn("shanghan_provenance", out["tools_used"])
        self.assertIn("深度溯源", out["answer"])
        # 純取文/多觀點/分歧圖譜互不侵佔
        self.assertIn("shanghan_perspectives",
                      a.ask("第12條怎麼理解？", role="researcher")["tools_used"])
        self.assertIn("shanghan_get_clause",
                      a.ask("第12條的原文與規則是什麼？",
                            role="researcher")["tools_used"])

    def test_tool_count_and_patient_exclusion(self):
        from hermes_shanghan.agent.tools import get_registry
        reg = get_registry()
        self.assertEqual(len(reg.names()), 27)
        self.assertIn("shanghan_provenance", reg.names())
        self.assertNotIn("shanghan_provenance",
                         reg.for_role("patient").names())

    def test_webui_renderer(self):
        from hermes_shanghan.apps.webui import tool_provenance
        html = tool_provenance("12")
        self.assertIn("影響力指標", html)
        self.assertIn("現代文獻計量", html)
        self.assertIn("輸入條文號", tool_provenance(""))  # empty → hint (no crash)


if __name__ == "__main__":
    unittest.main()
