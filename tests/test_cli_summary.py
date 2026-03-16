from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

ROOT_PATH = PROJECT_ROOT
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

import main
from data_analysis_agent.agent_runner import AgentStepTrace, AnalysisRunResult
from data_analysis_agent.data_context import DataContextSummary
from data_analysis_agent.reporting import ReportTelemetry


class CliSummaryTests(unittest.TestCase):
    def _build_result(self) -> AnalysisRunResult:
        run_dir = PROJECT_ROOT / "outputs" / "run_20260315_153022"
        data_dir = run_dir / "data"
        figures_dir = run_dir / "figures"
        logs_dir = run_dir / "logs"
        data_context = DataContextSummary(
            data_path=Path("data/simple_data.xls"),
            absolute_path=PROJECT_ROOT / "data" / "simple_data.xls",
            columns=["indicator", "2025-10"],
            dtypes="indicator object\n2025-10 float64",
            shape=(13, 2),
            head_markdown="| indicator | 2025-10 |",
            sample_size_warning="WARNING / 红色警告：当前样本量极小 (N<30)，强烈建议优先考虑非参数检验（如 Mann-Whitney U 检验），并对正态分布假设保持高度谨慎。",
            small_sample_warning=True,
            context_text="demo",
            input_kind="pdf",
            background_literature_context="CPI 代表居民消费价格指数。",
            pdf_multi_table_mode=True,
        )
        return AnalysisRunResult(
            data_context=data_context,
            raw_result="# Data Analysis Report",
            report_markdown="# Data Analysis Report",
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
                    decision="Search a term",
                    tool_name="TavilySearchTool",
                    tool_status="partial",
                    observation_preview="Skip online search",
                    summary="Online domain knowledge retrieval | status=partial",
                ),
            ),
            telemetry=ReportTelemetry(
                methods=("Descriptive statistics", "t-test"),
                domain="macroeconomics",
                tools_used=("PythonInterpreterTool", "TavilySearchTool"),
                search_used=False,
                search_notes="Tavily not configured, so online search was skipped.",
                cleaned_data_saved=True,
                cleaned_data_path=(data_dir / "cleaned_data.csv").as_posix(),
                figures_generated=((figures_dir / "chart.png").as_posix(),),
                valid=True,
                raw_payload={},
            ),
            methods_used=("Descriptive statistics", "t-test"),
            detected_domain="macroeconomics",
            tools_used=("PythonInterpreterTool", "TavilySearchTool"),
            search_status="skipped",
            search_notes="Tavily not configured, so online search was skipped.",
            workflow_complete=True,
            workflow_warnings=(),
            missing_artifacts=(),
            quality_mode="publication",
            review_enabled=True,
            review_status="accepted",
            review_rounds_used=1,
            review_critique="The report is publication-grade.",
            review_log_paths=(logs_dir / "review_round_1_review.json",),
            input_kind="pdf",
            document_ingestion_status="completed",
            document_ingestion_summary="PDF 主表已选定。",
            document_ingestion_duration_ms=1400,
            candidate_table_count=2,
            selected_table_id="table_01",
            pdf_multi_table_mode=True,
        )

    def test_format_search_status(self):
        text = main._format_search_status("skipped", "Tavily not configured, so online search was skipped.")
        self.assertIn("skipped", text.lower())

    def test_summary_table_contains_run_dir_and_trace(self):
        table = main._build_summary_table(self._build_result())
        rendered = "".join(str(column.header) for column in table.columns)
        self.assertIn("Field", rendered)
        self.assertEqual(len(table.rows), 28)


if __name__ == "__main__":
    unittest.main()
