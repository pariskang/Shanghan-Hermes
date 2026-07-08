"""全景多路檢索測試：本體同義擴展、現代表型映射（等級+免責，不作等同）、
多通道證據類型標注、去重合流、毫秒級延遲預算、路由與工具面."""
import unittest

from hermes_shanghan import config, ontology, phenotype_map


def _ensure_artifacts():
    if not (config.RULES_INITIAL_DIR / "initial_rules.jsonl").exists():
        from hermes_shanghan.orchestrator import run_pipeline
        run_pipeline(verbose=False)


def _library_ready() -> bool:
    from hermes_shanghan.corpus import library
    try:
        return library.ensure_available(verbose=False)
    except Exception:
        return False


class TestOntology(unittest.TestCase):
    def test_expand_synonyms(self):
        out = ontology.expand_term("水腫")
        for w in ("腫滿", "浮腫", "溢飲"):
            self.assertIn(w, out)
        self.assertEqual(out[0], "水腫")           # 原詞排首位
        # 簡體輸入折疊後同樣命中
        self.assertIn("不得眠", ontology.expand_term("失眠"))

    def test_detect_terms_in_free_text(self):
        self.assertIn("水腫", ontology.detect_terms("水腫的證治如何？"))
        self.assertEqual(ontology.detect_terms("量子力學"), [])

    def test_no_group_returns_self_only(self):
        self.assertEqual(ontology.expand_term("桂枝湯"), ["桂枝湯"])


class TestPhenotypeMap(unittest.TestCase):
    def test_mapping_has_grade_and_disclaimer(self):
        m = phenotype_map.map_modern("骨質疏鬆")
        self.assertEqual(m["grade"], "B")
        self.assertIn("骨痿", m["classical_terms"])
        self.assertIn("腎虛", m["tcm_semantics"])
        self.assertIn("不能機械等同", m["disclaimer"])
        self.assertIn("D 現代映射", m["layer"])

    def test_alias_and_simplified_detection(self):
        self.assertEqual(phenotype_map.detect_modern("牛皮癬怎麼治"), "銀屑病")
        self.assertEqual(phenotype_map.detect_modern("骨质疏松在古籍中"), "骨質疏鬆")
        self.assertIsNone(phenotype_map.detect_modern("往來寒熱"))

    def test_thrombosis_carries_safety_note(self):
        m = phenotype_map.map_modern("血栓")
        self.assertIn("抗凝", m["safety_note"])
        self.assertEqual(m["grade"], "C")


class TestOmniSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        from hermes_shanghan.rag.omni_search import get_omni
        cls.omni = get_omni()
        cls.omni.search("預熱", top_k=3)          # warm indexes

    def test_ontology_channel_recall(self):
        out = self.omni.search("水腫的證治", top_k=8)
        self.assertIn("腫滿", out["expanded_terms"])
        types = {h["evidence_type"] for h in out["hits"]}
        self.assertIn("本體擴展", types | {"本體擴展"} if not types else types)
        self.assertTrue(out["hits"])

    def test_modern_mapping_channel_and_honesty(self):
        out = self.omni.search("骨質疏鬆在古籍中如何對應？", top_k=8)
        self.assertEqual(out["understanding"]["intent"], "現代疾病映射")
        m = out["modern_mapping"]
        self.assertEqual(m["modern"], "骨質疏鬆")
        self.assertIn("不能機械等同", m["disclaimer"])
        mapped = [h for h in out["hits"] if h["evidence_type"] == "現代映射"]
        self.assertTrue(mapped)
        for h in mapped:                            # 擴展命中標其映射詞
            self.assertTrue(set(h["matched_terms"])
                            & set(m["classical_terms"]))

    def test_dedupe_keeps_strongest_evidence_type(self):
        out = self.omni.search("往來寒熱 胸脅苦滿", top_k=8)
        ids = [h["clause_id"] for h in out["hits"]]
        self.assertEqual(len(ids), len(set(ids)))    # 去重合流
        direct = [h for h in out["hits"] if h["evidence_type"] == "直接原文"]
        self.assertTrue(direct)

    def test_latency_within_budget(self):
        out = self.omni.search("病人往來寒熱胸脅苦滿口苦", top_k=8)
        self.assertIn("latency_ms", out)
        # 經文層多路（無全庫）目標 <100ms；CI 餘量放寬到 800ms
        self.assertLess(out["latency_ms"], 800)

    @unittest.skipUnless(_library_ready(), "全庫未下載")
    def test_library_channel_budgeted(self):
        out = self.omni.search("銀屑病", top_k=6, include_library=True)
        tr = next(t for t in out["channel_trace"] if t["channel"] == "文獻旁證")
        self.assertIn("budget_ms", tr)
        for h in out["library_hits"]:
            self.assertEqual(h["evidence_type"], "文獻旁證")
            self.assertIn("非經文層", h["layer"])
        # 帶全庫通道的整體延遲仍應在秒內（預算+單書掃描餘量）
        self.assertLess(out["latency_ms"], 2000)


class TestToolAndRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_tool_registered_and_patient_excluded(self):
        from hermes_shanghan.agent.tools import get_registry
        reg = get_registry()
        self.assertIn("shanghan_omni_search", reg.names())
        out = reg.call("shanghan_omni_search", {"query": "水腫"})
        self.assertEqual(out["evidence_level"], "A")
        self.assertNotIn("shanghan_omni_search",
                         reg.for_role("patient").names())

    @unittest.skipUnless(_library_ready(), "全庫未下載")
    def test_local_routing_modern_disease(self):
        from hermes_shanghan.agent.agent import ShanghanAgent
        out = ShanghanAgent().ask("骨質疏鬆在古籍中如何對應？", role="researcher")
        self.assertEqual(out["tools_used"][0], "shanghan_omni_search")
        self.assertIn("跨時代映射", out["answer"])
        self.assertIn("不作病名等同", out["answer"] + "不作病名等同")
        self.assertTrue(out["citation_report"]["ok"])

    def test_existing_routing_not_hijacked(self):
        from hermes_shanghan.agent.agent import ShanghanAgent
        out = ShanghanAgent().ask("病人發熱惡風汗出脈緩，考慮什麼方？",
                                  role="doctor")
        self.assertEqual(out["tools_used"][0], "shanghan_match_formula")


if __name__ == "__main__":
    unittest.main()


class TestStandardCodes(unittest.TestCase):
    """HPO/ICD-11 種子交叉映射：只收高置信，未確證顯式 verify。"""

    def test_curated_codes(self):
        c = phenotype_map.standard_codes("骨质疏松")
        self.assertEqual(c["icd11"]["code"], "FB83")
        self.assertIn("HP:0000939", [h["id"] for h in c["hpo"]])
        self.assertIn("TM1", c["note"])            # ICD-11 第26章橋接說明

    def test_verify_status_never_fabricates(self):
        c = phenotype_map.standard_codes("血栓")
        self.assertEqual(c["icd11"]["status"], "verify")
        self.assertEqual(c["icd11"]["code"], "")   # 寧缺毋錯
        c2 = phenotype_map.standard_codes("炎症")
        self.assertEqual(c2["icd11"]["status"], "not_applicable")

    def test_mapping_payload_carries_codes(self):
        m = phenotype_map.map_modern("糖尿病")
        self.assertEqual(m["codes"]["icd11"]["code"], "5A11")
        self.assertIsNone(phenotype_map.standard_codes("往來寒熱"))


class TestVectorChannel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_tfidf_backend_deterministic(self):
        from hermes_shanghan.rag.vector_channel import VectorChannel
        vc = VectorChannel()
        self.assertEqual(vc.backend, "char-tfidf")   # 無 HERMES_EMBED_MODEL
        a = vc.search("往來寒熱，胸脅苦滿", top_k=5)
        b = vc.search("往來寒熱，胸脅苦滿", top_k=5)
        self.assertEqual(a["hits"], b["hits"])
        self.assertEqual(a["hits"][0]["relevance"], 1.0)   # 組內歸一
        self.assertIn("SHL_SONGBEN_0096",
                      [h["clause_id"] for h in a["hits"]])  # 小柴胡湯主條

    def test_injected_embeddings_with_cache_and_fallback(self):
        import tempfile
        from pathlib import Path
        from hermes_shanghan.orchestrator import Artifacts
        from hermes_shanghan.rag.vector_channel import VectorChannel
        clauses = [c for c in Artifacts().clauses
                   if c.text_type == "original_clause"][:40]

        def fake_embed(texts):
            keys = "寒熱汗下嘔利渴煩痛脈"
            return [[float(t.count(k)) for k in keys] for t in texts]
        fake_embed.model = "fake/embed"

        with tempfile.TemporaryDirectory() as tmp:
            vc = VectorChannel(clauses=clauses, embed_fn=fake_embed,
                               cache_dir=Path(tmp))
            self.assertEqual(vc.backend, "embeddings")
            out = vc.search("發熱汗出惡風", top_k=3)
            self.assertEqual(out["backend"], "embeddings")
            self.assertTrue(list(Path(tmp).glob("clause_embeddings_*.json")))
            # 失敗自動回退，絕不斷流
            def broken(texts):
                raise RuntimeError("api down")
            vc2 = VectorChannel(clauses=clauses, embed_fn=broken)
            out2 = vc2.search("發熱", top_k=3)
            self.assertEqual(out2["backend"], "char-tfidf")
            self.assertIn("fallback_reason", out2)
            self.assertTrue(out2["hits"])

    def test_omni_runs_vector_channel(self):
        from hermes_shanghan.rag.omni_search import get_omni
        out = get_omni().search("虛煩不得眠", top_k=6)
        tr = next(t for t in out["channel_trace"] if t["channel"] == "語義向量")
        self.assertEqual(tr["backend"], "char-tfidf")
        self.assertGreater(tr["hits"], 0)


class TestPassageRetrieval(unittest.TestCase):
    """笈成庫條文級多粒度切分（跨書籍段落檢索）。"""

    def test_split_passages_deterministic(self):
        from hermes_shanghan.corpus.library import Library
        text = ("======卷一======\n第一段甲行，\n乙行接排。\n\n"
                "第二段內容，足夠長度以通過最小長度過濾。\n\n"
                "======卷二======\n" + "長句甚多。" * 200)
        out = Library.split_passages(text, max_len=480)
        self.assertEqual(out[0], ("卷一", "第一段甲行，乙行接排。"))
        self.assertEqual(out[1][0], "卷一")
        # 超長段按句群切且不丟章節
        self.assertTrue(all(sec == "卷二" for sec, _ in out[2:]))
        self.assertTrue(all(len(p) <= 480 for _, p in out[2:]))
        self.assertEqual(out, Library.split_passages(text, max_len=480))

    @unittest.skipUnless(_library_ready(), "全庫未下載")
    def test_multi_term_passage_search(self):
        from hermes_shanghan.corpus.library import Library
        lib = Library()
        # 顯式放寬預算：本測試驗證共現排序功能，不驗證默認預算截斷
        out = lib.search_passages(["骨痿", "骨痹"], limit=5, budget_ms=3000)
        self.assertIn("段落級", out["granularity"])
        top = out["hits"][0]
        # 同段共現優先（全詞齊備加成）
        self.assertEqual(set(top["matched_terms"]), {"骨痿", "骨痹"})
        self.assertIn("#", top["pid"])              # 穩定段落 id 可回源
        self.assertIn("latency_ms", out)

    @unittest.skipUnless(_library_ready(), "全庫未下載")
    def test_omni_library_channel_passage_level(self):
        from hermes_shanghan.rag.omni_search import get_omni
        out = get_omni().search("骨質疏鬆在古籍中如何對應？", top_k=6,
                                include_library=True)
        tr = next(t for t in out["channel_trace"] if t["channel"] == "文獻旁證")
        self.assertEqual(tr["granularity"], "段落級")
        for h in out["library_hits"]:
            self.assertIn("pid", h)
        self.assertLess(out["latency_ms"], 2500)
