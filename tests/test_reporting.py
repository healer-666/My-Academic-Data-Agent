from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.reporting import (
    convert_markdown_images_to_gradio_urls,
    extract_report_and_telemetry,
    normalize_markdown_image_paths,
)


class ReportingTests(unittest.TestCase):
    def test_valid_telemetry_is_extracted_and_stripped(self):
        raw = (
            "# Data Analysis Report\n\nReport body.\n\n"
            '<telemetry>{"methods":["t-test"],"domain":"finance","tools_used":["PythonInterpreterTool"],'
            '"search_used":false,"search_notes":"not used","cleaned_data_saved":true,'
            '"cleaned_data_path":"outputs/run/data/cleaned_data.csv","figures_generated":["outputs/run/figures/review_round_1/chart.png"]}</telemetry>'
        )

        result = extract_report_and_telemetry(raw)

        self.assertEqual(result.report_markdown, "# Data Analysis Report\n\nReport body.")
        self.assertTrue(result.telemetry.valid)
        self.assertEqual(result.telemetry.methods, ("t-test",))
        self.assertEqual(result.telemetry.domain, "finance")
        self.assertTrue(result.telemetry.cleaned_data_saved)
        self.assertEqual(result.telemetry.cleaned_data_path, "outputs/run/data/cleaned_data.csv")
        self.assertEqual(result.telemetry.figures_generated, ("outputs/run/figures/review_round_1/chart.png",))

    def test_malformed_telemetry_falls_back_safely(self):
        raw = "# Data Analysis Report\n\nReport body.\n\n<telemetry>{bad json}</telemetry>"

        result = extract_report_and_telemetry(raw)

        self.assertEqual(result.report_markdown, "# Data Analysis Report\n\nReport body.")
        self.assertFalse(result.telemetry.valid)
        self.assertIn("malformed", result.telemetry.warning or "")

    def test_missing_telemetry_uses_defaults(self):
        raw = "# Data Analysis Report\n\nReport only."

        result = extract_report_and_telemetry(raw)

        self.assertEqual(result.report_markdown, raw)
        self.assertFalse(result.telemetry.valid)
        self.assertEqual(result.telemetry.domain, "unknown")
        self.assertFalse(result.telemetry.cleaned_data_saved)

    def test_normalize_markdown_image_paths_converts_relative_outputs_path(self):
        figure_path = PROJECT_ROOT / "outputs" / "run_demo" / "figures" / "review_round_1" / "chart.png"
        figure_path.parent.mkdir(parents=True, exist_ok=True)
        figure_path.write_text("fake", encoding="utf-8")
        markdown = "![图表](outputs/run_demo/figures/review_round_1/chart.png)"

        normalized = normalize_markdown_image_paths(markdown, project_root=PROJECT_ROOT)

        self.assertIn(figure_path.resolve().as_posix(), normalized)

    def test_normalize_markdown_image_paths_keeps_absolute_paths(self):
        absolute = (PROJECT_ROOT / "outputs" / "run_demo" / "figures" / "chart_abs.png").resolve()
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_text("fake", encoding="utf-8")
        markdown = f"![图表]({absolute.as_posix()})"

        normalized = normalize_markdown_image_paths(markdown, project_root=PROJECT_ROOT)

        self.assertEqual(normalized, markdown)

    def test_normalize_markdown_image_paths_does_not_touch_standard_links(self):
        markdown = "[下载报告](outputs/run_demo/final_report.md)"

        normalized = normalize_markdown_image_paths(markdown, project_root=PROJECT_ROOT)

        self.assertEqual(normalized, markdown)

    def test_convert_markdown_images_to_gradio_urls_rewrites_image_targets(self):
        figure_path = PROJECT_ROOT / "outputs" / "run_demo" / "figures" / "review_round_1" / "chart_gradio.png"
        figure_path.parent.mkdir(parents=True, exist_ok=True)
        figure_path.write_text("fake", encoding="utf-8")
        markdown = "![图表](outputs/run_demo/figures/review_round_1/chart_gradio.png)"

        converted = convert_markdown_images_to_gradio_urls(markdown, project_root=PROJECT_ROOT)

        self.assertIn("/file=", converted)
        self.assertIn("chart_gradio.png", converted)


if __name__ == "__main__":
    unittest.main()
