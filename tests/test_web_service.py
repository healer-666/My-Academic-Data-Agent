from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.agent_runner import AgentStepTrace, AnalysisRunResult
from data_analysis_agent.data_context import DataContextSummary
from data_analysis_agent.reporting import ReportTelemetry
from data_analysis_agent.web.service import (
    answer_history_question_ui,
    copy_uploaded_file,
    create_run_bundle,
    load_history_qa_runs,
    stream_analysis_session,
)
from data_analysis_agent.web.viewmodels import default_max_reviews_for_quality, format_event_line


class WebServiceTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"web_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _build_result(self, run_dir: Path) -> AnalysisRunResult:
        data_dir = run_dir / "data"
        figures_dir = run_dir / "figures"
        logs_dir = run_dir / "logs"
        data_dir.mkdir(parents=True, exist_ok=True)
        (figures_dir / "review_round_1").mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        cleaned_data_path = data_dir / "cleaned_data.csv"
        cleaned_data_path.write_text("a,b\n1,2\n", encoding="utf-8")
        report_path = run_dir / "final_report.md"
        report_path.write_text("# Report", encoding="utf-8")
        trace_path = logs_dir / "agent_trace.json"
        trace_path.write_text("{}", encoding="utf-8")
        figure_path = figures_dir / "review_round_1" / "chart.png"
        figure_path.write_text("fake-image", encoding="utf-8")
        review_log_path = logs_dir / "review_round_1_review.json"
        review_log_path.write_text("{}", encoding="utf-8")
        ingestion_log_path = logs_dir / "document_ingestion.json"
        ingestion_log_path.write_text("{}", encoding="utf-8")

        data_context = DataContextSummary(
            data_path=Path("data/sample.csv"),
            absolute_path=PROJECT_ROOT / "data" / "sample.csv",
            columns=["col_a", "col_b"],
            dtypes="col_a int64\ncol_b float64",
            shape=(10, 2),
            head_markdown="| col_a | col_b |",
            sample_size_warning="",
            small_sample_warning=False,
            context_text="demo",
        )
        return AnalysisRunResult(
            data_context=data_context,
            raw_result="# Report",
            report_markdown="# Report\n\nDemo body.",
            report_path=report_path,
            output_dir=run_dir,
            run_dir=run_dir,
            data_dir=data_dir,
            figures_dir=figures_dir,
            logs_dir=logs_dir,
            trace_path=trace_path,
            cleaned_data_path=cleaned_data_path,
            agent_type="ScientificReActRunner",
            step_traces=(
                AgentStepTrace(
                    step_index=1,
                    raw_response="{}",
                    action="call_tool",
                    decision="Load data",
                    tool_name="PythonInterpreterTool",
                    tool_status="success",
                    observation_preview="Loaded data",
                    summary="Local Python analysis | status=success",
                ),
            ),
            telemetry=ReportTelemetry(
                methods=("Descriptive statistics",),
                domain="demo-domain",
                tools_used=("PythonInterpreterTool",),
                search_used=False,
                search_notes="not used",
                cleaned_data_saved=True,
                cleaned_data_path=cleaned_data_path.as_posix(),
                figures_generated=(figure_path.as_posix(),),
                valid=True,
                raw_payload={},
            ),
            methods_used=("Descriptive statistics",),
            detected_domain="demo-domain",
            tools_used=("PythonInterpreterTool",),
            search_status="not_used",
            search_notes="not used",
            workflow_complete=True,
            workflow_warnings=(),
            missing_artifacts=(),
            quality_mode="standard",
            review_enabled=True,
            review_status="accepted",
            review_rounds_used=1,
            review_critique="Accepted.",
            review_log_paths=(review_log_path,),
            input_kind="tabular",
            document_ingestion_status="not_needed",
            document_ingestion_summary="输入已是结构化表格，直接进入分析。",
            document_ingestion_duration_ms=0,
            document_ingestion_log_path=ingestion_log_path,
            latency_mode="auto",
            vision_review_mode="auto",
            rag_enabled=True,
            rag_status="retrieved",
            rag_match_count=2,
            rag_sources_used=("glossary.md",),
            rag_dense_match_count=1,
            rag_keyword_match_count=1,
            rag_retrieval_strategy="hybrid",
            rag_final_chunk_kinds=("text_section",),
            memory_enabled=True,
            memory_scope_key="project-alpha",
            memory_match_count=1,
            memory_writeback_status="written",
            memory_written_count=2,
        )

    def test_default_max_reviews_for_quality(self):
        self.assertEqual(default_max_reviews_for_quality("draft"), 0)
        self.assertEqual(default_max_reviews_for_quality("standard"), 1)
        self.assertEqual(default_max_reviews_for_quality("publication"), 2)

    def test_copy_uploaded_file_into_session_directory(self):
        case_dir = self._workspace_case_dir()
        upload = case_dir / "sample.csv"
        upload.write_text("a,b\n1,2\n", encoding="utf-8")

        copied = copy_uploaded_file(upload, uploads_root=case_dir / "uploads", session_id="session-123")

        self.assertTrue(copied.exists())
        self.assertEqual(copied.name, "sample.csv")
        self.assertIn("session-123", copied.as_posix())

    def test_create_run_bundle_creates_zip(self):
        case_dir = self._workspace_case_dir()
        run_dir = case_dir / "outputs" / "run_demo"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "final_report.md").write_text("# Report", encoding="utf-8")

        bundle = create_run_bundle(run_dir)

        self.assertTrue(bundle.exists())
        self.assertEqual(bundle.suffix, ".zip")

    def test_format_event_line_for_tabular_ingestion_skip(self):
        line = format_event_line("document_ingestion_skipped", {})
        self.assertIn("结构化表格", line)

    def test_load_history_qa_runs_uses_completed_records(self):
        records = (
            SimpleNamespace(
                run_id="run_demo",
                detected_domain="finance",
                review_status="accepted",
                timestamp="2026-04-14T10:00:00",
            ),
        )
        with patch("data_analysis_agent.web.service.index_completed_runs", return_value=records):
            choices, defaults = load_history_qa_runs("outputs")

        self.assertEqual(choices[0][1], "run_demo")
        self.assertEqual(defaults, ["run_demo"])

    def test_answer_history_question_ui_formats_sources_and_warnings(self):
        qa_result = SimpleNamespace(
            answer_markdown="## 历史问答结果\n\n这里是回答。",
            sources=("run_demo | report | review_status=accepted | 报告摘要",),
            warnings=("fallback used",),
        )
        with patch("data_analysis_agent.web.service.answer_history_question", return_value=qa_result):
            answer, sources_html = answer_history_question_ui(
                "上次用了什么方法？",
                ["run_demo"],
                "single",
                "outputs",
                "",
            )

        self.assertIn("这里是回答", answer)
        self.assertIn("run_demo", sources_html)
        self.assertIn("fallback used", sources_html)

    def test_stream_analysis_session_emits_final_outputs(self):
        case_dir = self._workspace_case_dir()
        upload = case_dir / "sample.csv"
        upload.write_text("a,b\n1,2\n", encoding="utf-8")
        knowledge = case_dir / "glossary.md"
        knowledge.write_text("Domain glossary.", encoding="utf-8")
        result = self._build_result(case_dir / "outputs" / "run_demo")

        def fake_run_analysis(*args, **kwargs):
            event_handler = kwargs["event_handler"]
            event_handler("config_loading", {})
            event_handler("document_ingestion_skipped", {})
            event_handler("analysis_started", {"analysis_round": 1, "max_steps": 6})
            event_handler("review_accepted", {"review_round": 1, "critique": "Accepted."})
            self.assertTrue(kwargs["use_rag"])
            self.assertTrue(kwargs["use_memory"])
            self.assertEqual(kwargs["memory_scope_key"], "project-alpha")
            self.assertEqual(len(kwargs["knowledge_paths"]), 1)
            return result

        with patch("data_analysis_agent.web.service.run_analysis", side_effect=fake_run_analysis):
            outputs = list(
                stream_analysis_session(
                    upload.as_posix(),
                    "demo query",
                    "standard",
                    "auto",
                    "auto",
                    6,
                    1,
                    3,
                    1024,
                    (case_dir / "outputs").as_posix(),
                    "Advanced Data Analyst",
                    "",
                    "demo-session",
                    [knowledge.as_posix()],
                    True,
                    True,
                    "project-alpha",
                )
            )

        final_output = outputs[-1]
        self.assertIn("运行完成", final_output[0])
        self.assertIn("demo-domain", final_output[2])
        self.assertIn("结构化表格", final_output[3])
        self.assertNotIn("PDF", final_output[3])
        self.assertIn("# Report", final_output[4])
        self.assertEqual(len(final_output[5]), 1)
        self.assertTrue(str(final_output[8]).endswith("final_report.md"))
        self.assertTrue(str(final_output[9]).endswith("agent_trace.json"))
        self.assertTrue(str(final_output[10]).endswith(".zip"))


if __name__ == "__main__":
    unittest.main()
