"""藥解/方解/煎服法模塊測試 — 混合規則+模型架構的可回歸驗證：
內證統計 A 錨定、種子詞典 D 標注、角色推導透明、方後原文逐字解析、
外用方識別、毒性/十八反安全審校、路由與患者隔離."""
import unittest

from hermes_shanghan import config, herb_lexicon


def _ensure_artifacts():
    if not (config.RULES_INITIAL_DIR / "initial_rules.jsonl").exists():
        from hermes_shanghan.orchestrator import run_pipeline
        run_pipeline(verbose=False)


def _registry():
    from hermes_shanghan.agent.tools import get_registry
    return get_registry()


class TestHerbLexicon(unittest.TestCase):
    def test_alias_and_info(self):
        self.assertEqual(herb_lexicon.canonical_herb("黃檗"), "黃柏")
        self.assertEqual(herb_lexicon.canonical_herb("白芍"), "芍藥")
        info = herb_lexicon.herb_info("附子")
        self.assertEqual(info["toxicity"], 2)
        self.assertTrue(info["pregnancy"])

    def test_toxicity_flags_and_shibafan(self):
        flags = herb_lexicon.toxicity_flags(["甘遂", "甘草", "大棗"])
        kinds = [f["kind"] for f in flags]
        self.assertIn("toxicity", kinds)
        self.assertIn("shibafan", kinds)        # 甘草×甘遂 觸十八反之誡
        sf = next(f for f in flags if f["kind"] == "shibafan")
        self.assertIn("甘遂", sf["with"])
        # 無同用則不誤報
        self.assertEqual([f["kind"] for f in
                          herb_lexicon.toxicity_flags(["桂枝", "芍藥"])], [])


class TestHerbCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        cls.reg = _registry()

    def test_card_layers_and_evidence(self):
        out = self.reg.call("shanghan_herb", {"herb": "桂枝"})
        self.assertIn("D", out["seed_knowledge"]["layer"])       # 本草通識標層
        self.assertIn("A", out["corpus_evidence"]["layer"])      # 內證統計標層
        self.assertGreaterEqual(out["corpus_evidence"]["n_formula_occurrences"], 30)
        first = out["corpus_evidence"]["formulas"][0]
        self.assertTrue(first["clause_id"].startswith("SHL_SONGBEN"))
        pairs = [p["paired_with"] for p in
                 out["corpus_evidence"]["frequent_pairs"]]
        self.assertIn("甘草", pairs)

    def test_toxic_herb_card_has_all_cautions(self):
        out = self.reg.call("shanghan_herb", {"herb": "附子"})
        kinds = {c["kind"] for c in out["cautions"]}
        self.assertLessEqual({"toxicity", "pregnancy"}, kinds)

    def test_disambiguation_and_unknown(self):
        out = self.reg.call("shanghan_herb", {"herb": "薑"})
        self.assertTrue(out["ambiguous"])
        self.assertIn("生薑", out["candidates"])
        out = self.reg.call("shanghan_herb", {"herb": "黃芪"})
        self.assertIn("未見", out["error"])


class TestFormulaExplain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        cls.reg = _registry()

    def test_guizhi_card_roles_transparent(self):
        out = self.reg.call("shanghan_formula_explain", {"formula": "桂枝湯"})
        roles = {a["herb"]: a for a in out["roles"]["assignments"]}
        self.assertIn("君", roles["桂枝"]["role"])
        self.assertIn("方以藥名", roles["桂枝"]["basis"])        # 推導依據可見
        self.assertIn("佐使", roles["甘草"]["role"])
        self.assertIn("D/E", out["roles"]["layer"])              # 誠實標層
        self.assertEqual(out["evidence_trace"]["block_clause_id"],
                         "SHL_SONGBEN_0012")
        # 配伍為 A 錨定共現統計
        self.assertTrue(any(p["n_formulas_together"] >= 10
                            for p in out["pairing"]))
        # 現代映射誠實地標記為 deferred，不憑空生成
        self.assertEqual(out["modern_mapping"]["status"], "deferred")

    def test_pathogenesis_binds_therapy_rules(self):
        out = self.reg.call("shanghan_formula_explain", {"formula": "麻黃湯"})
        self.assertIn("汗法", out["pathogenesis_therapy"]["therapeutic_methods"])

    def test_ambiguous_formula(self):
        out = self.reg.call("shanghan_formula_explain", {"formula": "桂枝"})
        self.assertTrue(out["ambiguous"])


class TestDecoction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        cls.reg = _registry()

    def _deco(self, formula):
        return self.reg.call("shanghan_decoction", {"formula": formula})

    def test_mahuang_pre_boil_verbatim(self):
        d = self._deco("麻黃湯")
        pre = next(s for s in d["steps"] if s["method"] == "先煮")
        self.assertEqual(pre["target"], "麻黃")
        self.assertIn("去上沫", pre["detail"] + pre["span"])
        self.assertEqual(pre["layer"], "A")                      # 逐字原文
        self.assertEqual(d["evidence_level"], "A")

    def test_ejiao_melt_and_jiu_medium(self):
        d = self._deco("炙甘草湯")
        self.assertTrue(any("清酒" in m["text"] for m in d["media"]))
        self.assertTrue(any(s["method"] == "烊化兌入" for s in d["steps"]))
        d2 = self._deco("黃連阿膠湯")
        methods = [s["method"] for s in d2["steps"]]
        self.assertIn("烊化兌入", methods)
        self.assertIn("後內", methods)                            # 內雞子黃

    def test_external_route_never_internal(self):
        d = self._deco("蜜煎導")
        self.assertIn("外用", d["route"])
        self.assertTrue(any(f["kind"] == "route" for f in d["safety_flags"]))

    def test_toxic_formula_triggers_safety(self):
        d = self._deco("十棗湯")
        kinds = {f["kind"] for f in d["safety_flags"]}
        self.assertIn("toxicity", kinds)
        self.assertTrue(any("強人" in a or "羸人" in a
                            for a in d["service"]["adjustments"]))
        # 漢制劑量警示永遠在場
        self.assertIn("dose_conversion", kinds)

    def test_guizhi_care_and_diet(self):
        d = self._deco("桂枝湯")
        care = "；".join(d["service"]["diet_and_care"])
        self.assertIn("粥", care)
        self.assertIn("禁生冷", care)
        self.assertTrue(any("停後服" in s or "不必盡劑" in s
                            for s in d["service"]["stop_rules"]))


class TestRoutingAndIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_local_routing(self):
        from hermes_shanghan.agent.agent import ShanghanAgent
        cases = {"桂枝湯的煎服法是什麼？": "shanghan_decoction",
                 "桂枝湯的方解和君臣佐使？": "shanghan_formula_explain",
                 "附子的性味功效是什麼？": "shanghan_herb"}
        for q, exp in cases.items():
            out = ShanghanAgent().ask(q, role="doctor")
            self.assertEqual(out["tools_used"][0], exp, q)
            self.assertTrue(out["citation_report"]["ok"], q)

    def test_formula_name_not_hijacked_by_herb_routing(self):
        from hermes_shanghan.agent.agent import ShanghanAgent
        out = ShanghanAgent().ask("桂枝湯的功效與方義？", role="doctor")
        self.assertEqual(out["tools_used"][0], "shanghan_formula_explain")

    def test_patient_cannot_reach_pharma_tools(self):
        reg = _registry().for_role("patient")
        for t in ("shanghan_herb", "shanghan_formula_explain",
                  "shanghan_decoction"):
            self.assertNotIn(t, reg.names())
            self.assertIn("out of scope", reg.call(t, {"formula": "桂枝湯",
                                                       "herb": "桂枝"}
                                                   if t == "shanghan_herb"
                                                   else {"formula": "桂枝湯"}
                                                   )["error"])


if __name__ == "__main__":
    unittest.main()
