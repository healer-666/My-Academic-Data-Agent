from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.rag.models import RetrievedChunk
from data_analysis_agent.reporting import (
    analyze_evidence_coverage,
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

    def test_valid_telemetry_normalizes_windows_style_paths(self):
        raw = (
            "# Data Analysis Report\n\nReport body.\n\n"
            '<telemetry>{"methods":["spearman"],"domain":"science","tools_used":["PythonInterpreterTool"],'
            '"search_used":false,"search_notes":"not used","cleaned_data_saved":true,'
            '"cleaned_data_path":"outputs\\\\run\\\\data\\\\cleaned_data.csv",'
            '"figures_generated":["figures\\\\review_round_2\\\\chart.png","chart2.png"]}</telemetry>'
        )

        result = extract_report_and_telemetry(raw)

        self.assertEqual(result.telemetry.cleaned_data_path, "outputs/run/data/cleaned_data.csv")
        self.assertEqual(
            result.telemetry.figures_generated,
            ("figures/review_round_2/chart.png", "chart2.png"),
        )

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

    def test_analyze_evidence_coverage_maps_inline_citations_to_register(self):
        report = (
            "# Data Analysis Report\n\n"
            "## Result Interpretation\n"
            "Biomarker A usually reflects inflammatory burden. [来源: glossary.md]\n\n"
            "## Discussion\n"
            "The literature context is consistent with the observed marker shift. [来源: guideline.md, p.2]"
        )

        coverage = analyze_evidence_coverage(
            report,
            evidence_register=(
                RetrievedChunk(
                    chunk_id="chunk-1",
                    text="Biomarker A usually reflects inflammatory burden.",
                    source_name="glossary.md",
                    source_path="memory/glossary.md",
                ),
                RetrievedChunk(
                    chunk_id="chunk-2",
                    text="Guideline note on biomarker interpretation.",
                    source_name="guideline.md",
                    source_path="memory/guideline.md",
                    page_number=2,
                ),
            ),
        )

        self.assertEqual(coverage.status, "covered")
        self.assertEqual(coverage.citation_count, 2)
        self.assertEqual(coverage.used_evidence_ids, ("RAG-glossary-md-chunk-1", "RAG-guideline-md-chunk-2"))
        self.assertEqual(coverage.cited_sources, ("glossary.md", "guideline.md"))

    def test_analyze_evidence_coverage_detects_invalid_and_missing_citations(self):
        report = (
            "# Data Analysis Report\n\n"
            "## Result Interpretation\n"
            "Biomarker A usually reflects inflammatory burden without attribution.\n\n"
            "## Discussion\n"
            "This conclusion cites a missing source. [来源: unknown.md, p.8]"
        )

        coverage = analyze_evidence_coverage(
            report,
            evidence_register=(
                RetrievedChunk(
                    chunk_id="chunk-1",
                    text="Biomarker A usually reflects inflammatory burden.",
                    source_name="glossary.md",
                    source_path="memory/glossary.md",
                ),
            ),
        )

        self.assertEqual(coverage.status, "invalid_and_missing")
        self.assertEqual(coverage.invalid_citation_labels, ("[来源: unknown.md, p.8]",))
        self.assertEqual(coverage.uncited_knowledge_sections_detected, ("Result Interpretation",))

    def test_analyze_evidence_coverage_ignores_guideline_word_in_data_filename(self):
        report = (
            "# 数据概览\n\n"
            "- 数据来源: `data/eval/reference_guideline_lookup.csv`\n"
            "- 变量: marker_level\n\n"
            "## 结论\n\n"
            "Marker-L 是一个示例性炎症相关指标。 [来源: reference_guideline_lookup.md]\n"
            "单次横截面数据只能支持差异性描述，不能证明因果关系。 [来源: reference_guideline_lookup.md]\n"
        )

        coverage = analyze_evidence_coverage(
            report,
            evidence_register=(
                RetrievedChunk(
                    chunk_id="chunk-1",
                    text="Marker-L 是一个示例性炎症相关指标。",
                    source_name="reference_guideline_lookup.md",
                    source_path="memory/reference_guideline_lookup.md",
                ),
            ),
        )

        self.assertEqual(coverage.status, "covered")
        self.assertEqual(coverage.uncited_knowledge_sections_detected, ())

    def test_analyze_evidence_coverage_does_not_require_citation_for_data_only_result_interpretation(self):
        report = (
            "# 数据概览\n\n"
            "Small tabular dataset.\n\n"
            "## 结果解释\n\n"
            "Treated 组的 Marker-L 中位数高于 control 组。"
            "Mann-Whitney U 检验显示两组分布差异具有统计学意义。"
            "效应量 r 达到最大值，提示两组间几乎无重叠。\n\n"
            "## 结论\n\n"
            "Marker-L 是一个示例性炎症相关指标。 [来源: reference_guideline_lookup.md]\n"
        )

        coverage = analyze_evidence_coverage(
            report,
            evidence_register=(
                RetrievedChunk(
                    chunk_id="chunk-1",
                    text="Marker-L 是一个示例性炎症相关指标。",
                    source_name="reference_guideline_lookup.md",
                    source_path="memory/reference_guideline_lookup.md",
                ),
            ),
        )

        self.assertEqual(coverage.status, "covered")
        self.assertEqual(coverage.uncited_knowledge_sections_detected, ())


if __name__ == "__main__":
    unittest.main()
