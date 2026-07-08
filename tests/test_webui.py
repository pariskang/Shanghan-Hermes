"""Gradio studio tests — skipped when gradio isn't installed (core stays
zero-dependency); handler logic is tested headless, no server launched."""
import json
import unittest

from hermes_shanghan import config

try:
    import gradio                                            # noqa: F401
    HAS_GRADIO = True
except ImportError:                                          # pragma: no cover
    HAS_GRADIO = False


def _ensure_artifacts():
    if not (config.RULES_INITIAL_DIR / "initial_rules.jsonl").exists():
        from hermes_shanghan.orchestrator import run_pipeline
        run_pipeline(verbose=False)


@unittest.skipUnless(HAS_GRADIO, "gradio not installed")
class TestWebUIHandlers(unittest.TestCase):
    """Handlers are plain functions over the agent stack — testable without
    a browser or a launched server."""

    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_chat_turn_populates_all_panels(self):
        from hermes_shanghan.apps.webui import chat_turn
        (hist, cleared, sess, log, ev, hyp, cons, cite,
         meta) = chat_turn("病人惡寒發熱無汗身疼痛，脈浮緊，考慮什麼方？",
                           [], "醫師", "單智能體", {}, [])
        self.assertEqual(len(hist), 2)
        self.assertEqual(cleared, "")
        self.assertIn("clause-card", ev)          # 檢索原文面板
        self.assertIn("hyp-card", hyp)            # 多假設面板
        self.assertIn("句級證據綁定率", cite)      # 核驗面板
        self.assertTrue(meta["trace"])
        self.assertEqual(len(log), 1)

    def test_council_mode_renders_adjudication(self):
        from hermes_shanghan.apps.webui import chat_turn
        *_, cons, cite, meta = chat_turn(
            "病人惡寒發熱無汗，會不會誤下成壞病？",
            [], "醫師", "多智能體合議", {}, [])
        self.assertIn("合議裁決", cons)

    def test_complex_mode_renders_task_graph(self):
        from hermes_shanghan.apps.webui import chat_turn
        *_, cite, meta = chat_turn(
            "少陰病寒化與熱化怎麼區分？分別有哪些主方和條文依據？",
            [], "科研", "複合編排", {}, [])
        self.assertIn("任務圖", cite)

    def test_patient_mode_guarded_through_ui(self):
        from hermes_shanghan.apps.webui import chat_turn
        hist, _, _, log, *_rest, meta = chat_turn(
            "我能不能喝桂枝湯？", [], "患者", "單智能體", {}, [])
        self.assertIn("安全守衛已攔截", meta["status"])
        self.assertNotIn("三兩", hist[-1]["content"])

    def test_export_roundtrip(self):
        from hermes_shanghan.apps.webui import chat_turn, export_conversation
        out = chat_turn("桂枝湯的方證要點？", [], "醫師", "單智能體", {}, [])
        log = out[3]
        p_md = export_conversation(log, "md")
        p_js = export_conversation(log, "json")
        self.assertTrue(p_md.endswith(".md"))
        data = json.loads(open(p_js, encoding="utf-8").read())
        self.assertEqual(data[0]["question"], "桂枝湯的方證要點？")
        self.assertIsNone(export_conversation([], "md"))

    def test_tool_handlers(self):
        from hermes_shanghan.apps import webui
        self.assertIn("clause-card", webui.tool_search("往來寒熱", 5, "", False))
        self.assertIn("SHL_SONGBEN_0012", webui.tool_holo("12"))
        self.assertIn("假設", webui.tool_hypotheses("惡寒、發熱、無汗", "脈浮緊", "", 4))
        self.assertIn("關鍵鑒別", webui.tool_differential("桂枝湯", "麻黃湯", ""))
        self.assertIn("藥量比", webui.tool_dose("桂枝湯", "三兩"))
        self.assertIn("禁忌檢查", webui.tool_contra("桂枝湯", "無汗"))

    def test_research_handler_produces_dossier_and_exports(self):
        from hermes_shanghan.apps.webui import run_research
        html, md, js = run_research("桂枝湯類方的劑量演化", 2)
        self.assertIn("研究問題細化", html)
        self.assertTrue(md.endswith(".md") and js.endswith(".json"))


@unittest.skipUnless(HAS_GRADIO, "gradio not installed")
class TestWebUIApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_artifacts()

    def test_app_builds(self):
        from hermes_shanghan.apps.webui import build_app, style_kwargs
        app = build_app()
        self.assertEqual(type(app).__name__, "Blocks")
        style = style_kwargs()
        self.assertIn("theme", style)
        self.assertIn("F7CAC9", style["css"])      # rose quartz present


if __name__ == "__main__":
    unittest.main()
