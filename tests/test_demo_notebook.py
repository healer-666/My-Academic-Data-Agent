from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DemoNotebookTests(unittest.TestCase):
    def test_demo_contains_trace_report_and_diagnostics_sections(self):
        notebook = json.loads((PROJECT_ROOT / "demo.ipynb").read_text(encoding="utf-8"))
        joined_sources = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
        )

        self.assertIn("render_trace_table", joined_sources)
        self.assertIn("render_full_report", joined_sources)
        self.assertIn("render_diagnostics", joined_sources)
        self.assertNotIn("print(result.report_markdown)", joined_sources)
