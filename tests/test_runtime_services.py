from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.artifact_service import build_run_context
from data_analysis_agent.doctor import run_doctor
from data_analysis_agent.events import EventRecorder
from data_analysis_agent.knowledge_context import KnowledgeContextProvider
from data_analysis_agent.runtime_models import WorkflowState
from data_analysis_agent.tooling_service import execute_tool_call


class _FakeRegistry:
    def list_tools(self):
        return ["PythonInterpreterTool"]

    def execute_tool(self, name, input_text):
        return '{"status":"success","text":"ok"}'


class RuntimeServiceTests(unittest.TestCase):
    def test_event_recorder_tracks_events_and_states(self):
        recorder = EventRecorder()
        recorder.emit("config_loading")
        recorder.emit("workflow_state_changed", workflow_state=WorkflowState.INGEST, state="ingest")

        events = recorder.snapshot()

        self.assertEqual(events[0].event_type.value, "config_loading")
        self.assertEqual(events[1].workflow_state, "ingest")
        self.assertEqual(events[1].payload["state"], "ingest")

    def test_execute_tool_call_returns_structured_missing_tool_error(self):
        result = execute_tool_call(
            tool_registry=_FakeRegistry(),
            tool_name="MissingTool",
            tool_input="demo",
            available_tools={"PythonInterpreterTool"},
        )

        self.assertEqual(result.tool_status, "error")
        self.assertIn("not registered", result.observation)

    def test_build_run_context_populates_paths_and_session(self):
        case_dir = PROJECT_ROOT / "tool-output" / "test-temp" / "runtime_services"
        case_dir.mkdir(parents=True, exist_ok=True)

        run_context = build_run_context(
            source_path=PROJECT_ROOT / "data" / "simple_data.xlsx",
            output_dir=case_dir,
            quality_mode="standard",
            latency_mode="auto",
            vision_review_mode="auto",
            document_ingestion_mode="auto",
            session_id="session-xyz",
        )

        self.assertEqual(run_context.session_id, "session-xyz")
        self.assertTrue(run_context.run_dir.name.startswith("run_"))
        self.assertTrue(run_context.cleaned_data_path.as_posix().endswith("cleaned_data.csv"))

    def test_knowledge_context_provider_collects_user_and_reference_context(self):
        ref_path = PROJECT_ROOT / "tool-output" / "test-temp" / "knowledge_ref.txt"
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text("Domain glossary for biomarker interpretation.", encoding="utf-8")

        class _DataContext:
            background_literature_context = "PDF abstract"

        bundle = KnowledgeContextProvider().collect(
            data_context=_DataContext(),
            user_query="Please focus on biomarker meaning.",
            reference_paths=(ref_path,),
        )

        rendered = bundle.render_for_prompt()
        self.assertIn("Please focus on biomarker meaning.", rendered)
        self.assertIn("knowledge_ref.txt", rendered)

    def test_run_doctor_reports_expected_checks(self):
        checks = run_doctor()
        names = {check.name for check in checks}

        self.assertIn("hello_agents", names)
        self.assertIn("rich", names)
        self.assertIn("gradio", names)
        self.assertIn("pdfplumber", names)


if __name__ == "__main__":
    unittest.main()
