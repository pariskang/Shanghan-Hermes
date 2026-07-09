"""溯源層（trace）測試：引文模式識別、統一 ID、學派/觀點、計量網絡、
五類溯源鏈、工具接線與可復現性。"""
import json
import unittest

from hermes_shanghan import config


def _ensure_artifacts():
    if not (config.RESEARCH_DIR / "commentary_divergence.json").exists():
        from hermes_shanghan.orchestrator import run_pipeline
        run_pipeline(verbose=False)
    from hermes_shanghan.trace.builder import ensure_built
    ensure_built()


# ---------------------------------------------------------------------------
# 引文模式識別（單元級：合成段落，不依賴掃描資產）
# ---------------------------------------------------------------------------
class TestQuotationScanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        from hermes_shanghan.trace.builder import _clause_texts
        from hermes_shanghan.trace.quotation import QuotationScanner
        cls.texts = _clause_texts()
        cls.scanner = QuotationScanner(cls.texts)

    def test_explicit_quote_detected_as_mingyin(self):
        t = self.texts["SHL_SONGBEN_0001"]
        edges, _ = self.scanner.scan_paragraph(f"仲景曰：{t}。此太陽之綱領也。")
        hit = next(e for e in edges if e["clause_id"] == "SHL_SONGBEN_0001")
        self.assertEqual(hit["mode"], "明引")
        self.assertGreaterEqual(hit["coverage"], 0.7)
        self.assertTrue(hit["marker"])

    def test_unmarked_full_quote_is_anyin(self):
        t = self.texts["SHL_SONGBEN_0012"]
        edges, _ = self.scanner.scan_paragraph(f"蓋{t}，此桂枝湯之正局。")
        hit = next(e for e in edges if e["clause_id"] == "SHL_SONGBEN_0012")
        self.assertEqual(hit["mode"], "暗引")

    def test_fragment_with_marker_is_jieyin(self):
        t = self.texts["SHL_SONGBEN_0016"]
        frag = t[:12]
        edges, _ = self.scanner.scan_paragraph(f"經云{frag}，法當隨證。")
        hit = next(e for e in edges if e["clause_id"] == "SHL_SONGBEN_0016")
        self.assertEqual(hit["mode"], "節引")

    def test_variant_glyphs_still_match(self):
        # 異體字（脅→脇）折疊後仍可回源
        edges, _ = self.scanner.scan_paragraph("仲景曰：往來寒熱，胸脇苦滿，嘿嘿不欲飲食。")
        self.assertTrue(any(e["clause_id"] == "SHL_SONGBEN_0096" for e in edges))

    def test_unresolved_marker_counted_not_fabricated(self):
        # 引《內經》語：庫內無此文 → 只計存疑，不得產生指向條文的邊
        edges, unresolved = self.scanner.scan_paragraph(
            "內經曰：陰陽者天地之道也，萬物之綱紀。")
        self.assertFalse([e for e in edges if e.get("longest_run", 0) >= 8])
        self.assertTrue(unresolved)

    def test_dialogue_marker_excluded(self):
        _, unresolved = self.scanner.scan_paragraph("問曰：何謂也？答曰：未知其詳。")
        self.assertEqual(unresolved, [])

    def test_selfcheck_benchmark(self):
        from hermes_shanghan.trace.quotation import selfcheck
        r = selfcheck(self.texts)
        for mode in ("明引", "節引", "暗引"):
            self.assertGreaterEqual(r["per_mode"][mode]["detection_rate"], 0.9)
            self.assertGreaterEqual(r["per_mode"][mode]["mode_agreement"], 0.9)
        self.assertGreaterEqual(r["per_mode"]["改寫"]["detection_rate"], 0.5)
        self.assertLessEqual(r["negative"]["false_positive_rate"], 0.05)


# ---------------------------------------------------------------------------
# 資產層：統一 ID / 引文邊 / 計量網絡 / 學派 / 觀點
# ---------------------------------------------------------------------------
class TestTraceAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_id_registry(self):
        from hermes_shanghan.trace.builder import load_registry
        reg = load_registry()
        self.assertEqual(reg["counts"]["works"], 57)
        self.assertGreaterEqual(reg["counts"]["formulas"], 100)
        # 朝代補注生效且標記透明
        jiyi = next(w for w in reg["works"] if w["book_dir"] == "傷寒論輯義")
        self.assertEqual(jiyi["dynasty"], "日本")
        self.assertTrue(jiyi["dynasty_overridden"])

    def test_citation_edges_aggregated(self):
        from hermes_shanghan.trace.builder import load_agg_edges
        rows = load_agg_edges()
        self.assertGreater(len(rows), 5000)
        r0 = rows[0]
        for key in ("book_dir", "clause_id", "modes", "max_coverage"):
            self.assertIn(key, r0)
        # A/B 層底本不得出現在引用方
        citing = {r["book_dir"] for r in rows}
        for base in (config.PRIMARY_BOOK, config.SONGBEN_FULL_BOOK,
                     *config.VARIANT_BOOKS):
            self.assertNotIn(base, citing)

    def test_network_metrics(self):
        from hermes_shanghan.trace.builder import load_network
        net = load_network()
        ov = net["overview"]
        self.assertGreater(ov["n_clause_edges"], 10000)
        self.assertGreater(ov["n_citing_works"], 30)
        self.assertTrue(net["top_cited_clauses"])
        self.assertTrue(net["cocitation_pairs"])
        self.assertTrue(net["bibliographic_coupling"])
        # 時間切片按朝代先後排序
        orders = [s["dynasty"] for s in net["time_slices"]]
        self.assertLess(orders.index("宋"), orders.index("清"))
        # 主路徑以原典起點
        mp = net["main_paths"][0]
        self.assertEqual(mp["path"][0]["book"], "傷寒論")

    def test_school_registry_grounded_in_atlas(self):
        from hermes_shanghan.trace.builder import load_schools
        reg = load_schools()
        self.assertEqual(reg["n_schools"], 10)
        cuojian = next(s for s in reg["schools"] if s["school_id"] == "SCH_CUOJIAN")
        self.assertEqual(cuojian["source_level"], "posthoc_induction")
        # 跨派一致度證據已回填（方有執所在派 vs 他派實測分歧）
        self.assertTrue(cuojian["agreement"]["most_divergent_cross_pairs"])

    def test_claims_grading_from_data(self):
        from hermes_shanghan.trace.builder import load_claims
        claims = load_claims()["claims"]
        gzt = next(c for c in claims if c["claim_id"] == "CLAIM_GZT_YINGWEI")
        # 「榮氣和/衛氣不和」逐字見於 53/54 條 → 原文直述成分必須被識別
        self.assertIn("原文直述成分", gzt["evidence_grade"])
        verbatim = gzt["terms_verbatim_in_original"]
        self.assertIn("SHL_SONGBEN_0053", sum(verbatim.values(), []))
        # 注家時間線按朝代排序且非空
        chron = gzt["commentarial_chronology"]
        self.assertTrue(chron)
        orders = [e["dynasty_order"] for e in chron]
        self.assertEqual(orders, sorted(orders))

    def test_rebuild_is_byte_identical(self):
        import hashlib
        from hermes_shanghan.trace.builder import build_all, trace_dir

        def digest():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(trace_dir().glob("*.json*"))}
        before = digest()
        build_all()
        self.assertEqual(before, digest())


# ---------------------------------------------------------------------------
# 五類溯源鏈
# ---------------------------------------------------------------------------
class TestChains(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_clause_chain(self):
        from hermes_shanghan.trace.chains import clause_chain
        r = clause_chain("12")
        self.assertEqual(r["chain_type"], "原文溯源鏈")
        self.assertEqual(r["clause"]["clause_id"], "SHL_SONGBEN_0012")
        self.assertTrue(r["variants"])            # B 層
        self.assertTrue(r["commentaries"])        # C 層
        self.assertGreater(r["citations"]["n_citing_books"], 10)
        self.assertEqual(r["main_path"][0]["dynasty"], "東漢")
        self.assertIn("A 原文直述", r["evidence_grade"])

    def test_formula_chain(self):
        from hermes_shanghan.trace.chains import formula_chain
        r = formula_chain("桂枝湯")
        self.assertEqual(r["chain_type"], "方劑源流鏈")
        self.assertTrue(r["earliest_source"]["clause_ids"])
        self.assertTrue(r["family_dose_evolution"])
        self.assertGreater(r["name_transmission"]["n_books"], 20)
        self.assertTrue(r["claims"])

    def test_claim_chain_finds_by_keyword(self):
        from hermes_shanghan.trace.chains import claim_chain
        r = claim_chain("營衛不和")
        self.assertEqual(r["chain_type"], "方證觀點演化鏈")
        self.assertEqual(r["formula"], "桂枝湯")
        self.assertTrue(r["commentarial_chronology"])

    def test_school_and_commentator_chains(self):
        from hermes_shanghan.trace.chains import commentator_chain, school_chain
        s = school_chain("錯簡重訂")
        self.assertEqual(s["school_id"], "SCH_CUOJIAN")
        self.assertTrue(s["member_citation_breadth"])
        c = commentator_chain("成無己")
        self.assertEqual(c["chain_type"], "注家解釋鏈")
        # 成注被大量後世著作轉引（張卿子本以成注為底本）
        self.assertGreater(c["relay_hub"]["n_relaying_books"], 5)
        top_books = [t["book"] for t in c["relay_hub"]["top"]]
        self.assertIn("張卿子傷寒論", top_books)

    def test_text_trace_grounds_fragment(self):
        from hermes_shanghan.trace.chains import text_trace
        r = text_trace("观其脉证，知犯何逆，随证治之")   # 簡體輸入亦可回源
        self.assertTrue(r["matches"])
        self.assertEqual(r["matches"][0]["clause_id"], "SHL_SONGBEN_0016")

    def test_text_trace_honest_on_foreign_text(self):
        from hermes_shanghan.trace.chains import text_trace
        r = text_trace("春三月此謂發陳天地俱生萬物以榮")
        self.assertFalse(r.get("matches"))
        self.assertIn("無可回源", r.get("note", ""))


# ---------------------------------------------------------------------------
# 工具接線與治理
# ---------------------------------------------------------------------------
class TestTraceTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()
        from hermes_shanghan.agent.tools import get_registry
        cls.reg = get_registry()

    def test_trace_tool_stamped_mixed_with_sections(self):
        out = self.reg.call("shanghan_trace", {"query_type": "clause", "ref": "12"})
        self.assertEqual(out["tool"], "shanghan_trace")
        # 整體 mixed，逐節單獨標層（審核意見 1）
        self.assertEqual(out["evidence_level"], "mixed")
        self.assertIn("limitations", out)
        sections = out["trace"]["section_evidence_levels"]
        self.assertEqual(sections["clause"], "A 原文直述")
        self.assertEqual(sections["commentaries"], "C 注家解釋")
        self.assertIn("clause_id", json.dumps(out, ensure_ascii=False))

    def test_network_scope_separation(self):
        # 正文/輔助篇章分榜（審核意見 2）：默認 canonical 不得混入 AUX
        out = self.reg.call("shanghan_citation_network", {})
        self.assertEqual(out["scope"], "canonical")
        ids = [c["clause_id"] for c in out["top_cited_clauses"]]
        self.assertTrue(ids)
        self.assertFalse([i for i in ids if "AUX" in i])
        aux = self.reg.call("shanghan_citation_network", {"scope": "auxiliary"})
        aux_ids = [c["clause_id"] for c in aux["top_cited_clauses"]]
        self.assertTrue(aux_ids)
        self.assertTrue(all("AUX" in i for i in aux_ids))
        self.assertTrue(aux.get("ranking_note"))
        # 主路徑基於正文榜
        from hermes_shanghan.trace.builder import load_network
        net = load_network()
        self.assertFalse([m for m in net["main_paths"]
                          if "AUX" in m["clause_id"]])

    def test_network_tool_formula_target(self):
        out = self.reg.call("shanghan_citation_network", {"target": "桂枝湯"})
        self.assertEqual(out["target"]["kind"], "formula")
        self.assertGreater(out["target"]["total_mentions"], 100)

    def test_trace_tools_not_patient_exposed(self):
        # 方劑源流鏈含組成/劑量 → 患者模式不暴露（硬隔離）
        scoped = self.reg.for_role("patient")
        self.assertNotIn("shanghan_trace", scoped.names())
        out = scoped.call("shanghan_trace", {"query_type": "clause", "ref": "12"})
        self.assertIn("error", out)

    def test_modern_interface_honest_default(self):
        from hermes_shanghan.trace.modern import load_modern_trace
        r = load_modern_trace()
        self.assertFalse(r["available"])
        self.assertIn("不隨庫分發", r["note"])

    def test_scan_library_with_fixture(self):
        # 全庫掃描（引用方=任意醫籍）：合成最小庫驗證端到端，不依賴真實下載
        import tempfile
        from pathlib import Path

        from hermes_shanghan.trace.builder import _clause_texts
        from hermes_shanghan.trace.quotation import scan_library
        texts = _clause_texts()
        clause1 = texts["SHL_SONGBEN_0001"]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            book = root / "books" / "測試醫籍"
            book.mkdir(parents=True)
            (book / "index.txt").write_text(
                "======測試醫籍======\n\n<book>\n書名=測試醫籍\n作者=測者\n"
                "朝代=清\n分類=傷寒\n</book>\n\n=====卷一=====\n\n"
                f"仲景曰：{clause1}。此論太陽之綱領也。\n",
                encoding="utf-8")
            (root / "catalog.json").write_text(json.dumps({
                "units": [{"id": "測試醫籍", "title": "測試醫籍", "author": "測者",
                           "dynasty": "清", "category": "傷寒",
                           "files": ["index.txt"], "parent": "", "sub_books": []}],
            }, ensure_ascii=False), encoding="utf-8")
            res = scan_library(texts, root=root)
            self.assertTrue(res["available"])
            hit = next(e for e in res["edges"]
                       if e["clause_id"] == "SHL_SONGBEN_0001")
            self.assertEqual(hit["mode"], "明引")
            self.assertEqual(hit["layer"], "旁證")
            self.assertEqual(hit["book"], "測試醫籍")
        with tempfile.TemporaryDirectory() as td:
            res = scan_library(texts, root=Path(td))
            self.assertFalse(res["available"])   # 未下載時如實返回，不觸發下載

    def test_research_loop_covers_citation_dimension(self):
        from hermes_shanghan.agent.research_loop import DeepResearcher
        d = DeepResearcher(max_rounds=3).run("桂枝湯的歷代引用與傳播")
        self.assertEqual(d["uncovered_dimensions"], [])
        self.assertGreaterEqual(d["coverage"]["引文傳播"], 1)
        f = next(f for f in d["findings"] if f["dimension"] == "引文傳播")
        self.assertTrue(f["citation_ok"])


if __name__ == "__main__":
    unittest.main()
