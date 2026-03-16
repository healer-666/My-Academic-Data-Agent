from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.agent_runner import AgentStepTrace, AnalysisRunResult
from data_analysis_agent.data_context import DataContextSummary
from data_analysis_agent.presentation import render_diagnostics, render_full_report, render_trace_table
from data_analysis_agent.reporting import ReportTelemetry


class PresentationTests(unittest.TestCase):
    def _build_result(self) -> AnalysisRunResult:
        run_dir = PROJECT_ROOT / "outputs" / "run_demo"
        data_dir = run_dir / "data"
        figures_dir = run_dir / "figures"
        logs_dir = run_dir / "logs"
        data_context = DataContextSummary(
            data_path=Path("data/sample.csv"),
            absolute_path=PROJECT_ROOT / "data" / "sample.csv",
            columns=["col_a", "col_b"],
            dtypes="col_a int64\ncol_b float64",
            shape=(10, 2),
            head_markdown="| col_a | col_b |",
            sample_size_warning="WARNING / 红色警告：当前样本量极小 (N<30)，强烈建议优先考虑非参数检验（如 Mann-Whitney U 检验），并对正态分布假设保持高度谨慎！",
            small_sample_warning=True,
            context_text="demo",
        )
        return AnalysisRunResult(
            data_context=data_context,
            raw_result="# Report",
            report_markdown="# Data Analysis Report\n\nA full markdown body.\n\n## Discussion\nMore detail here.",
            report_path=run_dir / "final_report.md",
            output_dir=run_dir,
            run_dir=run_dir,
            data_dir=data_dir,
            figures_dir=figures_dir,
            logs_dir=logs_dir,
            trace_path=logs_dir / "agent_trace.json",
            cleaned_data_path=data_dir / "cleaned_data.csv",
            agent_type="ScientificReActRunner",
            step_traces=(
                AgentStepTrace(
                    step_index=1,
                    raw_response="{}",
                    action="call_tool",
                    decision="Search the biomarker",
                    tool_name="TavilySearchTool",
                    tool_status="success",
                    observation="Search query: biomarker\n1. result",
                    observation_preview="Search query: biomarker",
                    summary="Online domain knowledge retrieval | status=success",
                ),
                AgentStepTrace(
                    step_index=2,
                    raw_response="{}",
                    action="call_tool",
                    decision="Run regression",
                    tool_name="PythonInterpreterTool",
                    tool_status="error",
                    observation="Python execution failed. Full traceback:\nTraceback (most recent call last):\nValueError: demo",
                    observation_preview="Python execution failed.",
                    summary="Local Python execution | status=error",
                ),
            ),
            telemetry=ReportTelemetry(
                methods=("Regression",),
                domain="biomedicine",
                tools_used=("PythonInterpreterTool", "TavilySearchTool"),
                search_used=True,
                search_notes="Online retrieval was used.",
                cleaned_data_saved=True,
                cleaned_data_path=data_dir.as_posix(),
                figures_generated=((figures_dir / "chart.png").as_posix(),),
                valid=True,
                raw_payload={},
            ),
            methods_used=("Regression",),
            detected_domain="biomedicine",
            tools_used=("PythonInterpreterTool", "TavilySearchTool"),
            search_status="used",
            search_notes="Online retrieval was used.",
            workflow_complete=False,
            workflow_warnings=("Missing cleaned data.",),
            missing_artifacts=((data_dir / "cleaned_data.csv").as_posix(),),
            quality_mode="publication",
            review_enabled=True,
            review_status="accepted",
            review_rounds_used=1,
            review_critique="Accepted after review.",
            review_log_paths=(logs_dir / "review_round_1_review.json",),
        )

    def test_render_trace_table_contains_tool_and_status(self):
        html_obj = render_trace_table(self._build_result())
        self.assertIn("TavilySearchTool", html_obj.data)
        self.assertIn("Stage / Tool", html_obj.data)

    def test_render_diagnostics_contains_full_traceback(self):
        html_obj = render_diagnostics(self._build_result())
        self.assertIn("Step 2 Traceback", html_obj.data)
        self.assertIn("Traceback (most recent call last)", html_obj.data)
        self.assertIn("ValueError: demo", html_obj.data)

    def test_render_full_report_preserves_markdown(self):
        markdown_obj = render_full_report(self._build_result())
        self.assertIn("## Discussion", markdown_obj.data)


if __name__ == "__main__":
    unittest.main()
