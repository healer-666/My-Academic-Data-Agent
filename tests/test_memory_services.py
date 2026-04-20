from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.config import RuntimeConfig
from data_analysis_agent.data_context import DataContextSummary
from data_analysis_agent.memory import (
    FailureMemoryRecord,
    FailureMemoryService,
    MemoryRecord,
    ProjectMemoryService,
    derive_memory_scope_key,
    extract_failure_memory_records,
    extract_memory_records,
)
from data_analysis_agent.reporting import ReportTelemetry
from data_analysis_agent.runtime_models import AnalysisRunResult


class _StubCollection:
    def __init__(self):
        self.run_ids: set[str] = set()
        self.records: list[tuple[str, str, dict[str, object]]] = []

    def get(self, where=None, include=None):
        where = where or {}
        if "run_id" in where:
            return {"ids": ["written"] if where["run_id"] in self.run_ids else []}
        if "memory_scope_key" in where:
            matched = [item for item in self.records if item[2].get("memory_scope_key") == where["memory_scope_key"]]
            return {"ids": [item[0] for item in matched]}
        return {"ids": [item[0] for item in self.records]}

    def upsert(self, *, ids, documents, metadatas, embeddings):
        for record_id, document, metadata in zip(ids, documents, metadatas):
            self.records.append((record_id, document, metadata))
            run_id = str(metadata.get("run_id", "") or "")
            if run_id:
                self.run_ids.add(run_id)

    def query(self, *, query_embeddings, n_results, where, include):
        matched = [item for item in self.records if item[2].get("memory_scope_key") == where.get("memory_scope_key")]
        documents = [item[1] for item in matched[:n_results]]
        metadatas = [item[2] for item in matched[:n_results]]
        return {"documents": [documents], "metadatas": [metadatas]}


class MemoryServiceTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"memory_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _build_result(self, run_dir: Path, *, review_status: str = "accepted") -> AnalysisRunResult:
        data_dir = run_dir / "data"
        figures_dir = run_dir / "figures"
        logs_dir = run_dir / "logs"
        data_dir.mkdir(parents=True, exist_ok=True)
        figures_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / "final_report.md"
        report_path.write_text(
            "# Report\n\n## Result Interpretation\nBiomarker A should be interpreted conservatively.\n\n## Discussion\nKeep claims non-causal.",
            encoding="utf-8",
        )
        trace_path = logs_dir / "agent_trace.json"
        trace_path.write_text("{}", encoding="utf-8")
        cleaned_data_path = data_dir / "cleaned_data.csv"
        cleaned_data_path.write_text("marker_a\n1\n", encoding="utf-8")
        data_context = DataContextSummary(
            data_path=Path("data/sample.csv"),
            absolute_path=PROJECT_ROOT / "data" / "sample.csv",
            columns=["marker_a", "marker_b"],
            dtypes="marker_a int64\nmarker_b int64",
            shape=(10, 2),
            head_markdown="| marker_a | marker_b |",
            sample_size_warning="",
            small_sample_warning=False,
            context_text="demo context",
        )
        return AnalysisRunResult(
            data_context=data_context,
            raw_result="# Report",
            report_markdown=report_path.read_text(encoding="utf-8"),
            report_path=report_path,
            output_dir=run_dir,
            run_dir=run_dir,
            data_dir=data_dir,
            figures_dir=figures_dir,
            logs_dir=logs_dir,
            trace_path=trace_path,
            cleaned_data_path=cleaned_data_path,
            agent_type="ScientificReActRunner",
            step_traces=(),
            telemetry=ReportTelemetry(
                methods=("Descriptive statistics",),
                domain="biomedicine",
                tools_used=("PythonInterpreterTool",),
                search_used=False,
                search_notes="",
                cleaned_data_saved=True,
                cleaned_data_path=cleaned_data_path.as_posix(),
                figures_generated=(),
                valid=True,
                raw_payload={},
            ),
            methods_used=("Descriptive statistics",),
            detected_domain="biomedicine",
            tools_used=("PythonInterpreterTool",),
            search_status="not_used",
            search_notes="",
            workflow_complete=True,
            workflow_warnings=(),
            missing_artifacts=(),
            quality_mode="standard",
            review_enabled=True,
            review_status=review_status,
            review_rounds_used=1,
            review_critique="Accepted.",
            review_log_paths=(),
            rag_enabled=True,
            rag_sources_used=("guideline.md",),
            rag_cited_sources=("guideline.md",),
            rag_evidence_coverage_status="covered",
        )

    def test_derive_memory_scope_key_prefers_session_label_and_falls_back_to_source_name(self):
        self.assertEqual(
            derive_memory_scope_key(session_label="Project Alpha", source_path="data/report.csv"),
            "project-alpha",
        )
        self.assertEqual(
            derive_memory_scope_key(source_path="data/My Sample File.xlsx"),
            "my-sample-file",
        )

    def test_extract_memory_records_builds_compact_record_set(self):
        result = self._build_result(self._workspace_case_dir() / "outputs" / "run_demo")

        extracted = extract_memory_records(
            result=result,
            review_history=(),
            memory_scope_key="project-alpha",
            llm=None,
        )

        self.assertGreaterEqual(len(extracted.records), 3)
        self.assertIn("analysis_summary", {record.memory_type for record in extracted.records})
        self.assertFalse(extracted.llm_distilled)
        self.assertTrue(all(record.memory_scope_key == "project-alpha" for record in extracted.records))

    def test_project_memory_service_write_is_idempotent_and_retrievable(self):
        collection = _StubCollection()
        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            embedding_model_id="text-embedding-demo",
            embedding_api_key="embed-key",
            embedding_base_url="https://embed.example.com/v1",
        )
        record = MemoryRecord(
            memory_id="memory-1",
            memory_scope_key="project-alpha",
            memory_type="analysis_summary",
            run_id="run_1",
            source_report_path="outputs/run_1/final_report.md",
            detected_domain="biomedicine",
            quality_mode="standard",
            created_at="2026-04-05T12:00:00",
            source_count=1,
            review_status="accepted",
            text="Use conservative biomarker interpretation.",
            source_names=("guideline.md",),
        )
        embed_stub = type("EmbedStub", (), {"embed_texts": staticmethod(lambda texts: [[0.1, 0.2] for _ in texts])})()
        with patch("data_analysis_agent.memory.service.OpenAIEmbeddingClient", return_value=embed_stub):
            service = ProjectMemoryService(runtime_config=runtime_config, memory_base_dir=self._workspace_case_dir() / "memory")
        with patch.object(service, "_get_collection", return_value=collection):
            write_one = service.write_records(records=(record,), run_id="run_1")
            write_two = service.write_records(records=(record,), run_id="run_1")
            retrieval = service.retrieve(
                memory_scope_key="project-alpha",
                user_query="Explain biomarker meaning",
                data_context=type("Ctx", (), {"columns": ["marker_a"], "selected_table_headers": (), "selected_table_numeric_columns": (), "background_literature_context": "", "selected_table_id": ""})(),
            )

        self.assertEqual(write_one.status, "written")
        self.assertEqual(write_two.status, "already_written")
        self.assertEqual(retrieval.status, "retrieved")
        self.assertEqual(retrieval.match_count, 1)
        prompt_text = service.format_for_prompt(retrieval.records)
        self.assertIn("analysis_summary", prompt_text)
        self.assertIn("Use conservative biomarker interpretation.", prompt_text)

    def test_extract_failure_memory_records_builds_negative_constraints(self):
        result = self._build_result(self._workspace_case_dir() / "outputs" / "run_failed", review_status="rejected")
        failed = AnalysisRunResult(
            **{
                **result.__dict__,
                "workflow_complete": False,
                "review_critique": "1. Do not use causal language.\n2. Recheck cleaned_data.csv reload.",
                "execution_audit_status": "failed",
                "execution_audit_passed": False,
                "execution_audit_findings": ("No later Python step explicitly reloaded cleaned_data.csv.",),
            }
        )

        extracted = extract_failure_memory_records(
            result=failed,
            review_history=(),
            memory_scope_key="project-alpha",
        )

        self.assertGreaterEqual(len(extracted.records), 2)
        self.assertTrue(all(record.usage_mode == "negative" for record in extracted.records))
        self.assertIn("failure_constraint", {record.failure_type for record in extracted.records})

    def test_failure_memory_service_write_is_idempotent_and_retrievable(self):
        collection = _StubCollection()
        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            embedding_model_id="text-embedding-demo",
            embedding_api_key="embed-key",
            embedding_base_url="https://embed.example.com/v1",
        )
        record = FailureMemoryRecord(
            memory_id="failure-1",
            memory_scope_key="project-alpha",
            failure_type="failure_constraint",
            run_id="run_fail_1",
            source_report_path="outputs/run_fail_1/final_report.md",
            source_trace_path="outputs/run_fail_1/logs/agent_trace.json",
            detected_domain="biomedicine",
            quality_mode="standard",
            created_at="2026-04-15T12:00:00",
            review_status="rejected",
            workflow_complete=False,
            execution_audit_status="failed",
            trigger_stage="review",
            text="Do not finish when reviewer-blocking issues remain unresolved.",
            avoidance_rule="Resolve reviewer-blocking issues before finish.",
            source_names=("guideline.md",),
        )
        embed_stub = type("EmbedStub", (), {"embed_texts": staticmethod(lambda texts: [[0.1, 0.2] for _ in texts])})()
        with patch("data_analysis_agent.memory.service.OpenAIEmbeddingClient", return_value=embed_stub):
            service = FailureMemoryService(runtime_config=runtime_config, memory_base_dir=self._workspace_case_dir() / "failure_memory")
        with patch.object(service, "_get_collection", return_value=collection):
            write_one = service.write_records(records=(record,), run_id="run_fail_1")
            write_two = service.write_records(records=(record,), run_id="run_fail_1")
            retrieval = service.retrieve(
                memory_scope_key="project-alpha",
                user_query="Avoid common reviewer failures",
                data_context=type("Ctx", (), {"columns": ["marker_a"], "selected_table_headers": (), "selected_table_numeric_columns": (), "background_literature_context": "", "selected_table_id": ""})(),
            )

        self.assertEqual(write_one.status, "written")
        self.assertEqual(write_two.status, "already_written")
        self.assertEqual(retrieval.status, "retrieved")
        self.assertEqual(retrieval.match_count, 1)
        prompt_text = service.format_for_prompt(retrieval.records)
        self.assertIn("AVOID", prompt_text)
        self.assertIn("Resolve reviewer-blocking issues", prompt_text)


if __name__ == "__main__":
    unittest.main()
