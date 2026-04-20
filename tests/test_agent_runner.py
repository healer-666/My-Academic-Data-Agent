from __future__ import annotations

import json
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

from data_analysis_agent.agent_runner import (
    ArtifactValidationResult,
    ScientificReActRunner,
    _build_reviewer_task,
    build_plaintext_event_handler,
    run_analysis,
)
from data_analysis_agent.config import RuntimeConfig
from data_analysis_agent.data_context import DataContextSummary
from data_analysis_agent.memory import (
    FailureMemoryRecord,
    FailureMemoryRetrievalResult,
    FailureMemoryWriteResult,
    MemoryRecord,
    MemoryRetrievalResult,
    MemoryWriteResult,
)
from data_analysis_agent.prompts import build_system_prompt
from data_analysis_agent.rag.models import RagIndexResult, RagRetrievalResult, RetrievedChunk
from data_analysis_agent.rag.query_builder import RetrievalQueryBundle
from data_analysis_agent.reporting import EvidenceCoverage, ReportTelemetry


def _finish_report(
    body: str,
    *,
    domain: str = "generic tabular data",
    cleaned: bool = False,
    cleaned_data_path: str = "",
) -> str:
    telemetry = {
        "methods": [],
        "domain": domain,
        "tools_used": [],
        "search_used": False,
        "search_notes": "not triggered",
        "cleaned_data_saved": cleaned,
        "cleaned_data_path": cleaned_data_path if cleaned_data_path else ("placeholder" if cleaned else ""),
        "figures_generated": [],
    }
    return f"# Data Analysis Report\n\n{body}\n\n<telemetry>{json.dumps(telemetry)}</telemetry>"


class StubLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if not self._responses:
            raise AssertionError("No more stubbed responses available.")
        return self._responses.pop(0)


class StubRegistry:
    def __init__(self, cleaned_data_path: Path | None = None):
        self.cleaned_data_path = cleaned_data_path
        self.calls = []

    def list_tools(self):
        return ["PythonInterpreterTool", "TavilySearchTool"]

    def get_tools_description(self):
        return "- PythonInterpreterTool: Execute Python code.\n- TavilySearchTool: Search the web."

    def execute_tool(self, name, input_text):
        self.calls.append((name, input_text))
        if name == "TavilySearchTool":
            return '{"status":"success","text":"Glossary note"}'
        if self.cleaned_data_path is not None:
            self.cleaned_data_path.parent.mkdir(parents=True, exist_ok=True)
            self.cleaned_data_path.write_text("a,b\n1,2\n", encoding="utf-8")
        return '{"status":"success","text":"cleaned_data saved"}'


class FakeRagService:
    COLLECTION_NAME = "academic_data_agent_knowledge"

    def __init__(self, *, runtime_config, knowledge_base_dir=None):
        self.runtime_config = runtime_config

    def index_files(self, knowledge_paths):
        return RagIndexResult(status="completed", indexed_documents=("glossary.md",), indexed_chunk_count=1, warnings=())

    def build_queries(self, *, data_context, user_query=""):
        return RetrievalQueryBundle("query", "dense", "keyword", ("marker_a",))

    def retrieve(self, **kwargs):
        chunk = RetrievedChunk(
            chunk_id="chunk-1",
            text="Biomarker A usually reflects inflammatory burden.",
            source_name="glossary.md",
            source_path="memory/glossary.md",
            knowledge_type="glossary",
            dense_score=0.9,
            keyword_score=2.0,
            match_reasons=("dense", "keyword"),
        )
        return RagRetrievalResult(
            status="retrieved",
            retrieval_query="query",
            dense_query="dense",
            keyword_query="keyword",
            chunks=(chunk,),
            dense_candidates=(chunk,),
            keyword_candidates=(chunk,),
            reranked_chunks=(chunk,),
            retrieval_strategy="hybrid",
            warnings=(),
        )


class FakeMemoryService:
    records = (
        MemoryRecord(
            memory_id="memory-1",
            memory_scope_key="project-alpha",
            memory_type="analysis_summary",
            run_id="run_previous",
            source_report_path="outputs/run_previous/final_report.md",
            detected_domain="biomedicine",
            quality_mode="standard",
            created_at="2026-04-05T12:00:00",
            source_count=1,
            review_status="accepted",
            text="Keep biomarker interpretation conservative and non-causal.",
            source_names=("guideline.md",),
        ),
    )
    last_written_run_id = ""

    def __init__(self, *, runtime_config, memory_base_dir=None):
        self.runtime_config = runtime_config

    def retrieve(self, *, memory_scope_key, user_query, data_context, top_k=4):
        return MemoryRetrievalResult(status="retrieved", memory_scope_key=memory_scope_key, retrieval_query="query", records=self.records)

    def format_for_prompt(self, records, *, max_chars=2200):
        return "\n".join(record.text for record in records)

    def write_records(self, *, records, run_id):
        self.__class__.last_written_run_id = run_id
        return MemoryWriteResult(status="written", written_records=tuple(records))


class FakeFailureMemoryService:
    records = (
        FailureMemoryRecord(
            memory_id="failure-1",
            memory_scope_key="project-alpha",
            failure_type="failure_constraint",
            run_id="run_previous_failed",
            source_report_path="outputs/run_previous_failed/final_report.md",
            source_trace_path="outputs/run_previous_failed/logs/agent_trace.json",
            detected_domain="biomedicine",
            quality_mode="standard",
            created_at="2026-04-05T12:00:00",
            review_status="rejected",
            workflow_complete=False,
            execution_audit_status="failed",
            trigger_stage="review",
            text="Do not finish while reviewer-blocking issues remain unresolved.",
            avoidance_rule="Resolve reviewer-blocking issues before finish.",
            source_names=("guideline.md",),
        ),
    )
    last_written_run_id = ""

    def __init__(self, *, runtime_config, memory_base_dir=None):
        self.runtime_config = runtime_config

    def retrieve(self, *, memory_scope_key, user_query, data_context, top_k=4):
        return FailureMemoryRetrievalResult(
            status="retrieved",
            memory_scope_key=memory_scope_key,
            retrieval_query="query",
            records=self.records,
        )

    def format_for_prompt(self, records, *, max_chars=2200):
        return "\n".join(record.text for record in records)

    def write_records(self, *, records, run_id):
        self.__class__.last_written_run_id = run_id
        return FailureMemoryWriteResult(status="written", written_records=tuple(records))


class AgentRunnerTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _runtime_config(self, *, embedding: bool = False) -> RuntimeConfig:
        return RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
            embedding_model_id="embed" if embedding else "",
            embedding_api_key="embed-key" if embedding else "",
            embedding_base_url="https://embed.example.com/v1" if embedding else "",
            embedding_timeout=30,
        )

    def test_plaintext_event_handler_is_callable(self):
        self.assertTrue(callable(build_plaintext_event_handler()))

    def test_runner_handles_tool_call_then_finish(self):
        llm = StubLLM(
            [
                '{"decision":"Search first","action":"call_tool","tool_name":"TavilySearchTool","tool_input":"CPI","final_answer":""}',
                '{"decision":"Analyze locally","action":"call_tool","tool_name":"PythonInterpreterTool","tool_input":"print(1)","final_answer":""}',
                json.dumps({"decision": "Done", "action": "finish", "tool_name": "", "tool_input": "", "final_answer": _finish_report("Complete.")}),
            ]
        )
        registry = StubRegistry()
        runner = ScientificReActRunner(
            name="Test Analyst",
            llm=llm,
            system_prompt=build_system_prompt(
                run_dir="outputs/run",
                cleaned_data_path="outputs/run/data/cleaned_data.csv",
                figures_dir="outputs/run/figures",
                logs_dir="outputs/run/logs",
                max_steps=4,
                tool_descriptions=registry.get_tools_description(),
            ),
            tool_registry=registry,
            max_steps=4,
        )

        final_answer, traces = runner.run("Please analyze the dataset")

        self.assertIn("<telemetry>", final_answer)
        self.assertEqual(len(traces), 3)
        self.assertEqual(traces[0].tool_name, "TavilySearchTool")
        self.assertEqual(traces[1].tool_name, "PythonInterpreterTool")
        self.assertEqual(traces[1].tool_input, "print(1)")

    def test_run_analysis_rejects_non_tabular_input(self):
        tmp_path = self._workspace_case_dir()
        pdf_path = tmp_path / "sample.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=self._runtime_config()):
            with self.assertRaises(ValueError) as context:
                run_analysis(pdf_path, output_dir=tmp_path / "outputs", quality_mode="draft")

        self.assertIn("CSV / XLS / XLSX", str(context.exception))

    def test_build_system_prompt_defaults_to_tabular_prompt(self):
        prompt = build_system_prompt(
            run_dir="outputs/run_demo",
            cleaned_data_path="outputs/run_demo/data/cleaned_data.csv",
            figures_dir="outputs/run_demo/figures",
            logs_dir="outputs/run_demo/logs",
            max_steps=4,
            tool_descriptions="- PythonInterpreterTool: Execute Python code.",
        )
        self.assertNotIn("<PDF_Small_Table_Mode>", prompt)
        self.assertNotIn("<PDF_Candidate_Tables_Context>", prompt)

    def test_run_analysis_records_tabular_ingestion_stub(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")
        llm = StubLLM([json.dumps({"decision": "Done", "action": "finish", "tool_name": "", "tool_input": "", "final_answer": _finish_report("Tabular mode.")})])

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=self._runtime_config(embedding=True)), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry", return_value=StubRegistry(cleaned_data_path=None)
        ):
            result = run_analysis(data_path, output_dir=tmp_path / "outputs", quality_mode="draft")

        self.assertEqual(result.input_kind, "tabular")
        self.assertEqual(result.document_ingestion_status, "not_needed")
        trace_payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
        self.assertEqual(trace_payload["run_metadata"]["input_kind"], "tabular")
        self.assertEqual(trace_payload["document_ingestion"]["status"], "not_needed")
        run_summary_payload = json.loads((result.run_dir / "run_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(run_summary_payload["run_id"], result.run_dir.name)
        self.assertIn("execution_audit_status", run_summary_payload)

    def test_build_reviewer_task_includes_generated_artifact_evidence(self):
        data_context = DataContextSummary(
            data_path=Path("data/sample.csv"),
            absolute_path=PROJECT_ROOT / "data" / "sample.csv",
            columns=["model", "precision"],
            dtypes="model object\nprecision float64",
            shape=(3, 2),
            head_markdown="| model | precision |",
            sample_size_warning="",
            small_sample_warning=False,
            context_text="demo context",
        )
        artifact_validation = ArtifactValidationResult(True, (), (), True, True, True)
        telemetry = ReportTelemetry(
            methods=("descriptive_statistics",),
            domain="computer vision",
            tools_used=("PythonInterpreterTool",),
            search_used=False,
            search_notes="",
            cleaned_data_saved=True,
            cleaned_data_path="outputs/run/data/cleaned_data.csv",
            figures_generated=("outputs/run_20260315_153022/figures/review_round_2/chart.png",),
            valid=True,
            raw_payload={},
        )
        report_path = PROJECT_ROOT / "outputs" / "run_20260315_153022" / "final_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        reviewer_task = _build_reviewer_task(
            data_context=data_context,
            report_markdown="# Report",
            report_path=report_path,
            step_traces=(),
            artifact_validation=artifact_validation,
            telemetry=telemetry,
            review_round=2,
            visual_review_summary="No major chart issues.",
            evidence_register=(RetrievedChunk(chunk_id="chunk-1", text="Guideline note.", source_name="guideline.md", source_path="memory/guideline.md", page_number=2),),
            evidence_coverage=EvidenceCoverage(status="missing_citations", citation_count=0, uncited_knowledge_sections_detected=("Discussion",)),
        )

        self.assertIn("Generated artifacts evidence", reviewer_task)
        self.assertIn("chart.png", reviewer_task)

    def test_run_analysis_injects_retrieved_knowledge_when_rag_enabled(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("marker_a,marker_b\n1,2\n", encoding="utf-8")
        knowledge_path = tmp_path / "glossary.md"
        knowledge_path.write_text("Biomarker A glossary entry.", encoding="utf-8")
        llm = StubLLM([json.dumps({"decision": "Done", "action": "finish", "tool_name": "", "tool_input": "", "final_answer": _finish_report("RAG mode.", domain="biomedicine")})])

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=self._runtime_config(embedding=True)), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry", return_value=StubRegistry(cleaned_data_path=None)
        ), patch("data_analysis_agent.agent_runner.RagService", FakeRagService):
            result = run_analysis(data_path, output_dir=tmp_path / "outputs", quality_mode="draft", use_rag=True, knowledge_paths=(knowledge_path,))

        self.assertEqual(result.rag_status, "retrieved")
        self.assertEqual(result.rag_sources_used, ("glossary.md",))
        self.assertEqual(result.rag_table_candidate_count, 0)
        self.assertFalse(result.rag_selected_table_hit)

    def test_run_analysis_injects_project_memory_and_writes_back_after_accept(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("marker_a,marker_b\n1,2\n", encoding="utf-8")
        fixed_run_dir = tmp_path / "outputs" / "run_fixed"
        (fixed_run_dir / "data").mkdir(parents=True, exist_ok=True)
        (fixed_run_dir / "figures").mkdir(parents=True, exist_ok=True)
        (fixed_run_dir / "logs").mkdir(parents=True, exist_ok=True)
        fixed_cleaned_path = fixed_run_dir / "data" / "cleaned_data.csv"
        llm = StubLLM(
            [
                json.dumps(
                    {
                        "decision": "Stage 1 save cleaned data",
                        "action": "call_tool",
                        "tool_name": "PythonInterpreterTool",
                        "tool_input": f'import pandas as pd\ndf = pd.read_csv(r"{data_path.as_posix()}")\ndf.to_csv(r"{fixed_cleaned_path.as_posix()}", index=False)\nprint("saved")',
                        "final_answer": "",
                    }
                ),
                json.dumps(
                    {
                        "decision": "Stage 2 reload cleaned data",
                        "action": "call_tool",
                        "tool_name": "PythonInterpreterTool",
                        "tool_input": f'import pandas as pd\ndf = pd.read_csv(r"{fixed_cleaned_path.as_posix()}")\nprint(df.shape)',
                        "final_answer": "",
                    }
                ),
                json.dumps(
                    {
                        "decision": "Done",
                        "action": "finish",
                        "tool_name": "",
                        "tool_input": "",
                        "final_answer": _finish_report(
                            "Memory mode.",
                            domain="biomedicine",
                            cleaned=True,
                            cleaned_data_path=fixed_cleaned_path.as_posix(),
                        ),
                    }
                ),
                '{"decision":"Accept","critique":"Looks good."}',
            ]
        )
        FakeMemoryService.last_written_run_id = ""

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=self._runtime_config(embedding=True)), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry", return_value=StubRegistry(cleaned_data_path=fixed_cleaned_path)
        ), patch(
            "data_analysis_agent.agent_runner._create_run_directory",
            return_value=(
                fixed_run_dir,
                fixed_run_dir / "data",
                fixed_run_dir / "figures",
                fixed_run_dir / "logs",
            ),
        ), patch(
            "data_analysis_agent.agent_runner.ProjectMemoryService", FakeMemoryService
        ), patch(
            "data_analysis_agent.agent_runner.FailureMemoryService", FakeFailureMemoryService
        ), patch(
            "data_analysis_agent.agent_runner.extract_memory_records", return_value=SimpleNamespace(records=FakeMemoryService.records, llm_distilled=False, warnings=())
        ):
            result = run_analysis(data_path, output_dir=tmp_path / "outputs", quality_mode="standard", use_memory=True, memory_scope_key="project-alpha")

        self.assertEqual(result.memory_scope_key, "project-alpha")
        self.assertEqual(result.memory_writeback_status, "written")
        self.assertEqual(result.memory_written_count, 1)
        self.assertEqual(result.failure_memory_writeback_status, "not_applicable")
        self.assertEqual(result.execution_audit_status, "passed")
        self.assertTrue(result.execution_audit_passed)
        self.assertTrue(FakeMemoryService.last_written_run_id.startswith("run_"))

    def test_run_analysis_hard_rejects_stage_contract_failure_before_reviewer(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")
        fixed_run_dir = tmp_path / "outputs" / "run_fixed_failure"
        (fixed_run_dir / "data").mkdir(parents=True, exist_ok=True)
        (fixed_run_dir / "figures").mkdir(parents=True, exist_ok=True)
        (fixed_run_dir / "logs").mkdir(parents=True, exist_ok=True)
        llm = StubLLM(
            [
                json.dumps(
                    {
                        "decision": "Finish without using cleaned dataset",
                        "action": "finish",
                        "tool_name": "",
                        "tool_input": "",
                        "final_answer": _finish_report("Failure mode.", domain="demo"),
                    }
                )
            ]
        )

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=self._runtime_config(embedding=True)), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry", return_value=StubRegistry(cleaned_data_path=None)
        ), patch(
            "data_analysis_agent.agent_runner.FailureMemoryService", FakeFailureMemoryService
        ), patch(
            "data_analysis_agent.agent_runner.extract_failure_memory_records",
            return_value=SimpleNamespace(records=FakeFailureMemoryService.records, warnings=()),
        ), patch(
            "data_analysis_agent.agent_runner._create_run_directory",
            return_value=(
                fixed_run_dir,
                fixed_run_dir / "data",
                fixed_run_dir / "figures",
                fixed_run_dir / "logs",
            ),
        ):
            result = run_analysis(
                data_path,
                output_dir=tmp_path / "outputs",
                quality_mode="standard",
                max_reviews=0,
            )

        self.assertEqual(result.execution_audit_status, "skipped")
        self.assertFalse(result.execution_audit_passed)
        self.assertEqual(result.review_status, "max_reviews_reached")
        self.assertIn("阶段执行审计未通过", result.review_critique)
        self.assertEqual(result.failure_memory_writeback_status, "written")


if __name__ == "__main__":
    unittest.main()
