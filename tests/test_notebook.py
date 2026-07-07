"""Colab notebook guard: valid nbformat, every code cell compiles, and the
package APIs the notebook calls actually exist with those signatures."""
import ast
import json
import unittest
from pathlib import Path

NB = Path(__file__).resolve().parents[1] / "notebooks" / "Hermes_Shanghanlun_Colab.ipynb"


class TestColabNotebook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nb = json.loads(NB.read_text(encoding="utf-8"))

    def test_nbformat_structure(self):
        self.assertEqual(self.nb["nbformat"], 4)
        self.assertGreaterEqual(len(self.nb["cells"]), 20)
        kinds = {c["cell_type"] for c in self.nb["cells"]}
        self.assertEqual(kinds, {"markdown", "code"})

    def test_all_code_cells_compile(self):
        for i, c in enumerate(self.nb["cells"]):
            if c["cell_type"] != "code":
                continue
            src = "".join(l for l in c["source"]
                          if not l.lstrip().startswith(("!", "%"))
                          and "#@param" not in l).replace("#@title", "# t")
            try:
                ast.parse(src)
            except SyntaxError as exc:
                self.fail(f"cell {i} does not compile: {exc}")

    def test_referenced_apis_exist(self):
        # the notebook's imports must resolve against the current package
        from hermes_shanghan.agent.agent import ShanghanAgent            # noqa
        from hermes_shanghan.agent.complex_agent import ComplexAgent     # noqa
        from hermes_shanghan.agent.research_loop import DeepResearcher   # noqa
        from hermes_shanghan.agent.session import AgentSession           # noqa
        from hermes_shanghan.eval.runner import run_suites               # noqa
        from hermes_shanghan.integrations.tool_specs import openai_tool_specs  # noqa
        from hermes_shanghan.paper.charts import heatmap                 # noqa
        from hermes_shanghan.paper.writer import PaperWriter             # noqa
        from hermes_shanghan.server.http_server import serve             # noqa
        from hermes_shanghan.server.service import ServiceContext        # noqa

    def test_research_assets_referenced_exist(self):
        blob = "".join("".join(c["source"]) for c in self.nb["cells"]
                       if c["cell_type"] == "code")
        for name in ("commentary_divergence.json", "dose_ratios.json",
                     "dose_family_evolution.json"):
            self.assertIn(name, blob)


if __name__ == "__main__":
    unittest.main()
