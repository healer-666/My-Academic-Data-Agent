from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.agent_runner import (
    ArtifactValidationResult,
    ScientificReActRunner,
    _build_reviewer_task,
    _build_observation_summary,
    _safe_parse_reviewer_reply,
    build_plaintext_event_handler,
    run_analysis,
)
from data_analysis_agent.config import RuntimeConfig
from data_analysis_agent.data_context import DataContextSummary
from data_analysis_agent.document_ingestion import IngestionResult
from data_analysis_agent.reporting import ReportTelemetry
from data_analysis_agent.prompts import build_system_prompt
from data_analysis_agent.vision_review import VisualReviewResult


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
    def __init__(self, cleaned_data_path: Path | None = None, *, include_tavily: bool = True):
        self.calls = []
        self.cleaned_data_path = cleaned_data_path
        self.include_tavily = include_tavily

    def list_tools(self):
        tools = ["PythonInterpreterTool"]
        if self.include_tavily:
            tools.append("TavilySearchTool")
        return tools

    def get_tools_description(self):
        descriptions = ["- PythonInterpreterTool: Execute Python code."]
        if self.include_tavily:
            descriptions.append("- TavilySearchTool: Search the web for domain knowledge.")
        return "\n".join(descriptions)

    def execute_tool(self, name, input_text):
        self.calls.append((name, input_text))
        if name == "TavilySearchTool":
            return '{"status":"success","text":"Search query: biomarker\\n1. Biomarker meaning\\n   URL: https://example.com"}'
        if self.cleaned_data_path is not None:
            self.cleaned_data_path.parent.mkdir(parents=True, exist_ok=True)
            self.cleaned_data_path.write_text("a,b\n1,2\n", encoding="utf-8")
        return '{"status":"success","text":"cleaned_data saved\\np-value=0.01\\nchart=figures/chart.png"}'


class AgentRunnerTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def test_plaintext_event_handler_is_callable(self):
        handler = build_plaintext_event_handler()
        self.assertTrue(callable(handler))

    def test_runner_handles_tool_call_then_finish(self):
        llm = StubLLM(
            [
                """
                {
                  "decision": "Search the acronym before interpreting the result.",
                  "action": "call_tool",
                  "tool_name": "TavilySearchTool",
                  "tool_input": "What does CPI mean in economics?",
                  "final_answer": ""
                }
                """,
                """
                {
                  "decision": "Load the cleaned dataset and inspect summary statistics.",
                  "action": "call_tool",
                  "tool_name": "PythonInterpreterTool",
                  "tool_input": "print('summary ok')",
                  "final_answer": ""
                }
                """,
                """
                {
                  "decision": "The analysis is complete.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nComplete.\\n\\n## Methodology\\nDescriptive statistics and t-test.\\n\\n## Core Hypothesis-Testing Conclusions\\np-value = 0.01.\\n\\n## Result Interpretation\\nStatistical evidence was found.\\n\\n## Discussion\\nDomain context was incorporated.\\n\\nCleaned data path: outputs/run/data/cleaned_data.csv\\n\\n![Chart](outputs/run/figures/chart.png)\\n\\n<telemetry>{\\"methods\\": [\\"Descriptive statistics\\", \\"t-test\\"], \\"domain\\": \\"macroeconomics\\", \\"tools_used\\": [\\"PythonInterpreterTool\\", \\"TavilySearchTool\\"], \\"search_used\\": true, \\"search_notes\\": \\"Used CPI background knowledge.\\", \\"cleaned_data_saved\\": true, \\"cleaned_data_path\\": \\"outputs/run/data/cleaned_data.csv\\", \\"figures_generated\\": [\\"outputs/run/figures/chart.png\\"]}</telemetry>"
                }
                """,
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

        final_answer, traces = runner.run("Please analyze the dataset:\nRelative path: data/simple_data.xls")

        self.assertIn("<telemetry>", final_answer)
        self.assertEqual(len(traces), 3)
        self.assertEqual(traces[0].tool_name, "TavilySearchTool")
        self.assertEqual(traces[0].tool_status, "success")
        self.assertIn("Online domain knowledge retrieval", traces[0].summary)
        self.assertEqual(traces[1].tool_name, "PythonInterpreterTool")
        self.assertEqual(registry.calls[0][0], "TavilySearchTool")

    def test_runner_recovers_from_fenced_json(self):
        llm = StubLLM(
            [
                """```json
                {
                  "decision": "Finish directly for parser validation.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\nParsing test complete.\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": []}</telemetry>"
                }
                ```"""
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
                max_steps=2,
                tool_descriptions=registry.get_tools_description(),
            ),
            tool_registry=registry,
            max_steps=2,
        )

        final_answer, traces = runner.run("Please analyze the dataset:\nRelative path: data/simple_data.xls")

        self.assertIn("Parsing test complete", final_answer)
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].action, "finish")

    def test_run_analysis_creates_run_directory_and_trace(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "Clean the raw file and save cleaned data first.",
                  "action": "call_tool",
                  "tool_name": "PythonInterpreterTool",
                  "tool_input": "print('cleaning complete')",
                  "final_answer": ""
                }
                """,
                """
                {
                  "decision": "The report is complete.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nDone.\\n\\n## Methodology\\nDescriptive statistics.\\n\\n## Core Hypothesis-Testing Conclusions\\nNo formal test.\\n\\n## Result Interpretation\\nStable.\\n\\n## Discussion\\nNone.\\n\\nCleaned data path: placeholder\\n\\n<telemetry>{\\"methods\\": [\\"Descriptive statistics\\"], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [\\"PythonInterpreterTool\\"], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": true, \\"cleaned_data_path\\": \\"placeholder\\", \\"figures_generated\\": []}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Accept",
                  "critique": "The report is publication-grade and internally coherent."
                }
                """,
            ]
        )

        expected_registry: dict[str, StubRegistry] = {}

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ):
            with patch("data_analysis_agent.agent_runner.build_tool_registry") as registry_builder:
                def side_effect(*args, **kwargs):
                    registry = StubRegistry(cleaned_data_path=expected_registry["cleaned_data_path"])
                    expected_registry["registry"] = registry
                    return registry

                registry_builder.side_effect = side_effect

                with patch("data_analysis_agent.agent_runner._create_run_directory") as create_run_dir:
                    run_dir = tmp_path / "outputs" / "run_20260315_153022"
                    data_dir = run_dir / "data"
                    figures_dir = run_dir / "figures"
                    logs_dir = run_dir / "logs"
                    for directory in (data_dir, figures_dir, logs_dir):
                        directory.mkdir(parents=True, exist_ok=True)
                    expected_registry["cleaned_data_path"] = data_dir / "cleaned_data.csv"
                    create_run_dir.return_value = (run_dir, data_dir, figures_dir, logs_dir)

                    result = run_analysis(data_path, output_dir=tmp_path / "outputs", quality_mode="standard")

        self.assertEqual(result.run_dir.name, "run_20260315_153022")
        self.assertTrue(result.report_path.exists())
        self.assertEqual(result.report_path.name, "final_report.md")
        self.assertTrue(result.trace_path.exists())
        self.assertTrue(result.cleaned_data_path.exists())
        self.assertTrue(result.workflow_complete)
        self.assertEqual(result.review_status, "accepted")
        self.assertEqual(result.quality_mode, "standard")
        self.assertTrue(result.review_enabled)
        self.assertEqual(result.review_rounds_used, 1)
        self.assertEqual(len(result.review_log_paths), 1)
        self.assertTrue(result.review_log_paths[0].exists())
        self.assertTrue((result.figures_dir / "review_round_1").exists())

        trace_payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
        self.assertEqual(trace_payload["run_metadata"]["run_dir"], result.run_dir.as_posix())
        self.assertTrue(trace_payload["artifact_validation"]["workflow_complete"])
        self.assertEqual(trace_payload["review_status"], "accepted")
        self.assertEqual(len(trace_payload["review_history"]), 1)

    def test_run_analysis_marks_missing_cleaned_data_as_incomplete(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "Go straight to a final answer.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nDone.\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": []}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Reject",
                  "critique": "The cleaned dataset artifact is missing, so the report cannot pass review."
                }
                """,
            ]
        )

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry", return_value=StubRegistry(cleaned_data_path=None)
        ):
            result = run_analysis(data_path, output_dir=tmp_path / "outputs", max_reviews=0, quality_mode="standard")

        self.assertFalse(result.workflow_complete)
        self.assertIn(result.cleaned_data_path.as_posix(), result.missing_artifacts)
        self.assertEqual(result.review_status, "max_reviews_reached")
        self.assertEqual(result.review_rounds_used, 1)

    def test_run_analysis_skips_reviewer_in_draft_mode(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "Clean the raw file and save cleaned data first.",
                  "action": "call_tool",
                  "tool_name": "PythonInterpreterTool",
                  "tool_input": "print('cleaning complete')",
                  "final_answer": ""
                }
                """,
                """
                {
                  "decision": "The draft report is complete.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nDraft mode.\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [\\"PythonInterpreterTool\\"], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": true, \\"cleaned_data_path\\": \\"placeholder\\", \\"figures_generated\\": []}</telemetry>"
                }
                """,
            ]
        )

        expected_registry: dict[str, StubRegistry] = {}

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ):
            with patch("data_analysis_agent.agent_runner.build_tool_registry") as registry_builder:
                def side_effect(*args, **kwargs):
                    registry = StubRegistry(cleaned_data_path=expected_registry["cleaned_data_path"])
                    expected_registry["registry"] = registry
                    return registry

                registry_builder.side_effect = side_effect

                with patch("data_analysis_agent.agent_runner._create_run_directory") as create_run_dir:
                    run_dir = tmp_path / "outputs" / "run_20260315_153022"
                    data_dir = run_dir / "data"
                    figures_dir = run_dir / "figures"
                    logs_dir = run_dir / "logs"
                    for directory in (data_dir, figures_dir, logs_dir):
                        directory.mkdir(parents=True, exist_ok=True)
                    expected_registry["cleaned_data_path"] = data_dir / "cleaned_data.csv"
                    create_run_dir.return_value = (run_dir, data_dir, figures_dir, logs_dir)

                    result = run_analysis(data_path, output_dir=tmp_path / "outputs", quality_mode="draft")

        self.assertEqual(result.quality_mode, "draft")
        self.assertFalse(result.review_enabled)
        self.assertEqual(result.review_status, "skipped")
        self.assertEqual(result.review_rounds_used, 0)
        self.assertEqual(len(result.review_log_paths), 0)

    def test_run_analysis_reinjects_reviewer_critique_for_revision(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "Clean the raw file and save cleaned data first.",
                  "action": "call_tool",
                  "tool_name": "PythonInterpreterTool",
                  "tool_input": "print('cleaning complete')",
                  "final_answer": ""
                }
                """,
                """
                {
                  "decision": "Draft the first report.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nDraft one.\\n\\n## Methodology\\nDescriptive statistics.\\n\\n## Core Hypothesis-Testing Conclusions\\nNo formal test.\\n\\n## Result Interpretation\\nThis causes an outcome.\\n\\n## Discussion\\nInitial draft.\\n\\n![Chart](outputs/run_20260315_153022/figures/review_round_1/chart.png)\\n\\nCleaned data path: placeholder\\n\\n<telemetry>{\\"methods\\": [\\"Descriptive statistics\\"], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [\\"PythonInterpreterTool\\"], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": true, \\"cleaned_data_path\\": \\"placeholder\\", \\"figures_generated\\": [\\"outputs/run_20260315_153022/figures/review_round_1/chart.png\\"]}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Reject",
                  "critique": "Remove the causal language and tighten the interpretation."
                }
                """,
                """
                {
                  "decision": "Revise the report after review.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nDraft two.\\n\\n## Methodology\\nDescriptive statistics.\\n\\n## Core Hypothesis-Testing Conclusions\\nNo formal test.\\n\\n## Result Interpretation\\nThe variables are associated.\\n\\n## Discussion\\nRevised after review.\\n\\n![Chart](outputs/run_20260315_153022/figures/review_round_2/chart.png)\\n\\nCleaned data path: placeholder\\n\\n<telemetry>{\\"methods\\": [\\"Descriptive statistics\\"], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [\\"PythonInterpreterTool\\"], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": true, \\"cleaned_data_path\\": \\"placeholder\\", \\"figures_generated\\": [\\"outputs/run_20260315_153022/figures/review_round_2/chart.png\\"]}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Accept",
                  "critique": "The revised report is acceptable."
                }
                """,
            ]
        )

        expected_registry: dict[str, StubRegistry] = {}

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ):
            with patch("data_analysis_agent.agent_runner.build_tool_registry") as registry_builder:
                def side_effect(*args, **kwargs):
                    registry = StubRegistry(cleaned_data_path=expected_registry["cleaned_data_path"])
                    expected_registry["registry"] = registry
                    return registry

                registry_builder.side_effect = side_effect

                with patch("data_analysis_agent.agent_runner._create_run_directory") as create_run_dir:
                    run_dir = tmp_path / "outputs" / "run_20260315_153022"
                    data_dir = run_dir / "data"
                    figures_dir = run_dir / "figures"
                    logs_dir = run_dir / "logs"
                    for directory in (data_dir, figures_dir, logs_dir):
                        directory.mkdir(parents=True, exist_ok=True)
                    expected_registry["cleaned_data_path"] = data_dir / "cleaned_data.csv"
                    create_run_dir.return_value = (run_dir, data_dir, figures_dir, logs_dir)

                    result = run_analysis(data_path, output_dir=tmp_path / "outputs", max_reviews=1, quality_mode="publication")

        self.assertEqual(result.review_status, "accepted")
        self.assertEqual(result.quality_mode, "publication")
        self.assertTrue(result.review_enabled)
        self.assertEqual(result.review_rounds_used, 2)
        self.assertIn("acceptable", result.review_critique.lower())
        self.assertEqual(len(result.review_log_paths), 2)
        second_round_messages = llm.calls[3]
        self.assertTrue(any("[审稿人拒稿意见]" in message["content"] for message in second_round_messages if "content" in message))
        self.assertTrue(any("逐条回应并修复以下全部问题" in message["content"] for message in second_round_messages if "content" in message))
        self.assertTrue((result.figures_dir / "review_round_1").exists())
        self.assertTrue((result.figures_dir / "review_round_2").exists())
        self.assertTrue((result.run_dir / "review_round_1_report.md").exists())
        self.assertTrue((result.run_dir / "review_round_2_report.md").exists())
        self.assertIn("review_round_2/chart.png", result.report_markdown)
        self.assertNotIn("review_round_1/chart.png", result.report_markdown)

    def test_run_analysis_standard_mode_allows_one_revision_by_default(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "Create the first draft.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nStandard draft one.\\n\\n![Chart](outputs/run_20260315_153022/figures/review_round_1/chart.png)\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": [\\"outputs/run_20260315_153022/figures/review_round_1/chart.png\\"]}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Reject",
                  "critique": "Please revise the chart path and clarify the wording."
                }
                """,
                """
                {
                  "decision": "Create the revised draft.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nStandard draft two.\\n\\n![Chart](outputs/run_20260315_153022/figures/review_round_2/chart.png)\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": [\\"outputs/run_20260315_153022/figures/review_round_2/chart.png\\"]}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Accept",
                  "critique": "The revised standard-mode report is acceptable."
                }
                """,
            ]
        )

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry", return_value=StubRegistry(cleaned_data_path=None)
        ):
            result = run_analysis(data_path, output_dir=tmp_path / "outputs", quality_mode="standard")

        self.assertEqual(result.review_status, "accepted")
        self.assertEqual(result.review_rounds_used, 2)
        self.assertEqual(len(result.review_log_paths), 2)
        self.assertIn("review_round_2/chart.png", result.report_markdown)

    def test_run_analysis_publication_mode_allows_two_revisions_by_default(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "Publication draft one.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\nDraft 1\\n\\n![Chart](outputs/run_20260315_153022/figures/review_round_1/chart.png)\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": [\\"outputs/run_20260315_153022/figures/review_round_1/chart.png\\"]}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Reject",
                  "critique": "First rejection."
                }
                """,
                """
                {
                  "decision": "Publication draft two.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\nDraft 2\\n\\n![Chart](outputs/run_20260315_153022/figures/review_round_2/chart.png)\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": [\\"outputs/run_20260315_153022/figures/review_round_2/chart.png\\"]}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Reject",
                  "critique": "Second rejection."
                }
                """,
                """
                {
                  "decision": "Publication draft three.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\nDraft 3\\n\\n![Chart](outputs/run_20260315_153022/figures/review_round_3/chart.png)\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": [\\"outputs/run_20260315_153022/figures/review_round_3/chart.png\\"]}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Accept",
                  "critique": "Accepted after two revisions."
                }
                """,
            ]
        )

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry", return_value=StubRegistry(cleaned_data_path=None)
        ):
            result = run_analysis(data_path, output_dir=tmp_path / "outputs", quality_mode="publication")

        self.assertEqual(result.review_status, "accepted")
        self.assertEqual(result.review_rounds_used, 3)
        self.assertEqual(len(result.review_log_paths), 3)
        self.assertIn("review_round_3/chart.png", result.report_markdown)

    def test_invalid_reviewer_output_falls_back_to_reject(self):
        reply = _safe_parse_reviewer_reply("not-json")

        self.assertEqual(reply.decision, "Reject")
        self.assertIn("could not be parsed", reply.critique)

    def test_observation_summary_compresses_python_output(self):
        observation = json.dumps(
            {
                "status": "success",
                "text": "Long python output",
                "data": {
                    "stdout": "A" * 1400,
                    "stderr": "B" * 900,
                    "warnings": [f"warning-{index}" for index in range(7)],
                },
            }
        )

        summary = _build_observation_summary(
            tool_name="PythonInterpreterTool",
            observation=observation,
            tool_status="success",
            observation_preview="python preview",
        )

        self.assertIn("Stdout:", summary)
        self.assertIn("Stderr:", summary)
        self.assertIn("[truncated]", summary)
        self.assertIn("more warning(s) omitted", summary)

    def test_observation_summary_compresses_tavily_results(self):
        observation = json.dumps(
            {
                "status": "success",
                "text": "Search results",
                "data": {
                    "query": "NIPT threshold",
                    "results": [
                        {"title": f"Result {index}", "url": f"https://example.com/{index}", "content": "C" * 260}
                        for index in range(4)
                    ],
                },
            }
        )

        summary = _build_observation_summary(
            tool_name="TavilySearchTool",
            observation=observation,
            tool_status="success",
            observation_preview="search preview",
        )

        self.assertIn("Top search results", summary)
        self.assertIn("NIPT threshold", summary)
        self.assertIn("more result(s) omitted", summary)

    def test_run_analysis_auto_mode_reduces_effective_steps_and_records_timing(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "The report is complete.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nAuto mode.\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": []}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Accept",
                  "critique": "Acceptable."
                }
                """,
            ]
        )

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry", return_value=StubRegistry(cleaned_data_path=None, include_tavily=False)
        ):
            result = run_analysis(
                data_path,
                output_dir=tmp_path / "outputs",
                quality_mode="standard",
                latency_mode="auto",
                max_steps=6,
            )

        trace_payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
        self.assertEqual(result.latency_mode, "auto")
        self.assertEqual(trace_payload["run_metadata"]["effective_max_steps"], 4)
        self.assertIn("total_duration_ms", trace_payload["timing_breakdown"])
        self.assertIn("llm_duration_ms", trace_payload["step_traces"][0])

    def test_run_analysis_publication_auto_injects_visual_review_summary(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
            vision_model_id="vision-demo-model",
            vision_api_key="vision-demo-key",
            vision_base_url="https://vision.example.com/v1",
            vision_timeout=45,
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "Clean the raw file and save cleaned data first.",
                  "action": "call_tool",
                  "tool_name": "PythonInterpreterTool",
                  "tool_input": "print('cleaning complete')",
                  "final_answer": ""
                }
                """,
                """
                {
                  "decision": "The report is complete.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nVisual review demo.\\n\\n## Methodology\\nDescriptive statistics.\\n\\n## Core Hypothesis-Testing Conclusions\\nNo formal test.\\n\\n## Result Interpretation\\nAssociation only.\\n\\n## Discussion\\nVisual reviewer should audit the chart.\\n\\n![Chart](outputs/run_20260315_153022/figures/review_round_1/chart.png)\\n\\nCleaned data path: placeholder\\n\\n<telemetry>{\\"methods\\": [\\"Descriptive statistics\\"], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [\\"PythonInterpreterTool\\"], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": true, \\"cleaned_data_path\\": \\"placeholder\\", \\"figures_generated\\": [\\"outputs/run_20260315_153022/figures/review_round_1/chart.png\\"]}</telemetry>"
                }
                """,
                """
                {
                  "decision": "Accept",
                  "critique": "The report is acceptable after the visual audit."
                }
                """,
            ]
        )

        expected_registry: dict[str, StubRegistry] = {}

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch("data_analysis_agent.agent_runner.run_visual_review") as visual_review_mock:
            visual_review_mock.return_value = VisualReviewResult(
                status="completed",
                decision="Flag",
                summary="热图标签略显拥挤，建议旋转横轴标签。",
                figures_reviewed=("outputs/run_20260315_153022/figures/review_round_1/chart.png",),
                skipped_figures=(),
                duration_ms=1200,
                raw_response='{"decision":"Flag","summary":"热图标签略显拥挤，建议旋转横轴标签。","findings":[]}',
            )
            with patch("data_analysis_agent.agent_runner.build_tool_registry") as registry_builder:
                def side_effect(*args, **kwargs):
                    registry = StubRegistry(cleaned_data_path=expected_registry["cleaned_data_path"], include_tavily=False)
                    expected_registry["registry"] = registry
                    return registry

                registry_builder.side_effect = side_effect

                with patch("data_analysis_agent.agent_runner._create_run_directory") as create_run_dir:
                    run_dir = tmp_path / "outputs" / "run_20260315_153022"
                    data_dir = run_dir / "data"
                    figures_dir = run_dir / "figures"
                    logs_dir = run_dir / "logs"
                    review_round_dir = figures_dir / "review_round_1"
                    for directory in (data_dir, figures_dir, review_round_dir, logs_dir):
                        directory.mkdir(parents=True, exist_ok=True)
                    (review_round_dir / "chart.png").write_bytes(b"fake-png")
                    expected_registry["cleaned_data_path"] = data_dir / "cleaned_data.csv"
                    create_run_dir.return_value = (run_dir, data_dir, figures_dir, logs_dir)

                    result = run_analysis(
                        data_path,
                        output_dir=tmp_path / "outputs",
                        quality_mode="publication",
                        vision_review_mode="auto",
                    )

        self.assertEqual(result.vision_review_mode, "auto")
        self.assertTrue(result.vision_review_enabled)
        self.assertEqual(result.vision_review_status, "completed")
        self.assertEqual(result.vision_review_summary, "热图标签略显拥挤，建议旋转横轴标签。")
        self.assertEqual(result.vision_review_duration_ms, 1200)
        self.assertEqual(len(result.vision_review_log_paths), 1)
        self.assertTrue(result.vision_review_log_paths[0].exists())

        reviewer_messages = llm.calls[-1]
        reviewer_prompt = reviewer_messages[1]["content"]
        self.assertIn("Visual figure audit summary", reviewer_prompt)
        self.assertIn("热图标签略显拥挤，建议旋转横轴标签。", reviewer_prompt)

        trace_payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
        self.assertEqual(trace_payload["run_metadata"]["vision_review_mode"], "auto")
        self.assertTrue(trace_payload["run_metadata"]["vision_configured"])
        self.assertEqual(trace_payload["timing_breakdown"]["vision_review_duration_ms"], 1200)
        self.assertEqual(len(trace_payload["vision_review_history"]), 1)

    def test_run_analysis_fast_mode_disables_tavily_without_strong_signal(self):
        tmp_path = self._workspace_case_dir()
        data_path = tmp_path / "sample.csv"
        data_path.write_text("a,b\n1,2\n", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key="demo-tavily-key",
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "Draft mode report.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nFast mode.\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": []}</telemetry>"
                }
                """,
            ]
        )

        captured_kwargs: dict[str, object] = {}

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch("data_analysis_agent.agent_runner.build_tool_registry") as registry_builder:
            def side_effect(*args, **kwargs):
                captured_kwargs.update(kwargs)
                return StubRegistry(cleaned_data_path=None, include_tavily=False)

            registry_builder.side_effect = side_effect
            result = run_analysis(
                data_path,
                output_dir=tmp_path / "outputs",
                quality_mode="draft",
                latency_mode="fast",
                query="Please summarize this small table.",
            )

        self.assertFalse(captured_kwargs["enable_search"])
        self.assertEqual(result.search_status, "not_used")

    def test_run_analysis_pdf_input_uses_document_ingestion_result(self):
        tmp_path = self._workspace_case_dir()
        pdf_path = tmp_path / "sample.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "The report is complete.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nPDF mode.\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": []}</telemetry>"
                }
                """,
            ]
        )

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry", return_value=StubRegistry(cleaned_data_path=None, include_tavily=False)
        ), patch("data_analysis_agent.agent_runner.ingest_input_document") as ingest_mock:
            normalized_csv = tmp_path / "outputs" / "run_20260315_153022" / "data" / "extracted_tables" / "table_01.csv"
            normalized_csv.parent.mkdir(parents=True, exist_ok=True)
            normalized_csv.write_text("x,y\n1,2\n", encoding="utf-8")
            parsed_document = tmp_path / "outputs" / "run_20260315_153022" / "data" / "parsed_document.json"
            parsed_document.parent.mkdir(parents=True, exist_ok=True)
            parsed_document.write_text(
                json.dumps({"background_literature_context": "BMI 代表身体质量指数。"}, ensure_ascii=False),
                encoding="utf-8",
            )
            ingest_mock.return_value = IngestionResult(
                input_kind="pdf",
                status="completed",
                summary="PDF 文档解析完成。",
                normalized_data_path=normalized_csv,
                duration_ms=900,
                log_path=tmp_path / "outputs" / "run_20260315_153022" / "logs" / "document_ingestion.json",
                parsed_document_path=parsed_document,
                selected_table_id="table_01",
                background_literature_context="BMI 代表身体质量指数。",
            )

            result = run_analysis(
                pdf_path,
                output_dir=tmp_path / "outputs",
                quality_mode="draft",
                document_ingestion_mode="text_only",
            )

        self.assertEqual(result.input_kind, "pdf")
        self.assertEqual(result.document_ingestion_status, "completed")
        self.assertEqual(result.document_ingestion_duration_ms, 900)
        ingest_mock.assert_called_once()
        trace_payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
        self.assertEqual(trace_payload["run_metadata"]["input_kind"], "pdf")
        self.assertEqual(trace_payload["document_ingestion"]["status"], "completed")
        self.assertEqual(trace_payload["timing_breakdown"]["document_ingestion_duration_ms"], 900)

    def test_run_analysis_pdf_ingestion_failure_stops_before_analyst_loop(self):
        tmp_path = self._workspace_case_dir()
        pdf_path = tmp_path / "sample.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
        )

        llm = StubLLM([])

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry", return_value=StubRegistry(cleaned_data_path=None, include_tavily=False)
        ), patch("data_analysis_agent.agent_runner.ingest_input_document") as ingest_mock:
            ingest_mock.return_value = IngestionResult(
                input_kind="pdf",
                status="failed",
                summary="PDF 解析失败：未提取到满足主表路由规则的结构化表格。",
                normalized_data_path=tmp_path / "outputs" / "run_x" / "data" / "cleaned_data.csv",
                duration_ms=800,
            )

            with self.assertRaises(ValueError) as context:
                run_analysis(
                    pdf_path,
                    output_dir=tmp_path / "outputs",
                    quality_mode="draft",
                    document_ingestion_mode="text_only",
                )

        self.assertIn("PDF 解析失败", str(context.exception))
        self.assertEqual(llm.calls, [])


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
        artifact_validation = ArtifactValidationResult(
            workflow_complete=True,
            missing_artifacts=(),
            warnings=(),
            cleaned_data_exists=True,
            report_exists=True,
            trace_exists=True,
        )
        telemetry = ReportTelemetry(
            methods=("descriptive_statistics",),
            domain="computer vision",
            tools_used=("PythonInterpreterTool",),
            search_used=False,
            search_notes="",
            cleaned_data_saved=True,
            cleaned_data_path="outputs/run/data/cleaned_data.csv",
            figures_generated=(
                "outputs/run_20260315_153022/figures/review_round_2/chart.png",
                "outputs/run_20260315_153022/figures/review_round_1/old_chart.png",
            ),
            valid=True,
            raw_payload={},
        )
        report_path = PROJECT_ROOT / "outputs" / "run_20260315_153022" / "final_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        (report_path.parent / "figures" / "review_round_2").mkdir(parents=True, exist_ok=True)

        reviewer_task = _build_reviewer_task(
            data_context=data_context,
            report_markdown="# Report",
            report_path=report_path,
            step_traces=(),
            artifact_validation=artifact_validation,
            telemetry=telemetry,
            review_round=2,
            visual_review_summary="No major chart issues.",
        )

        self.assertIn("Generated artifacts evidence", reviewer_task)
        self.assertIn("review_round_figures_generated_count: 1", reviewer_task)
        self.assertIn("chart.png", reviewer_task)
        self.assertIn("artifact_workflow_complete: True", reviewer_task)

    def test_build_system_prompt_mentions_pdf_small_table_constraints(self):
        prompt = build_system_prompt(
            run_dir="outputs/run_demo",
            cleaned_data_path="outputs/run_demo/data/cleaned_data.csv",
            figures_dir="outputs/run_demo/figures",
            logs_dir="outputs/run_demo/logs",
            max_steps=4,
            tool_descriptions="- PythonInterpreterTool: Execute Python code.",
            background_literature_context="Model comparison table from a PDF paper.",
            pdf_small_table_mode=True,
        )

        self.assertIn("<PDF_Small_Table_Mode>", prompt)
        self.assertIn("Do not introduce one-sample tests", prompt)

    def test_run_analysis_passes_selected_table_id_to_document_ingestion(self):
        tmp_path = self._workspace_case_dir()
        pdf_path = tmp_path / "sample.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")

        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            timeout=30,
            tavily_api_key=None,
        )

        llm = StubLLM(
            [
                """
                {
                  "decision": "The report is complete.",
                  "action": "finish",
                  "tool_name": "",
                  "tool_input": "",
                  "final_answer": "# Data Analysis Report\\n\\n## Data Overview\\nPDF mode.\\n\\n<telemetry>{\\"methods\\": [], \\"domain\\": \\"generic tabular data\\", \\"tools_used\\": [], \\"search_used\\": false, \\"search_notes\\": \\"not triggered\\", \\"cleaned_data_saved\\": false, \\"cleaned_data_path\\": \\"\\", \\"figures_generated\\": []}</telemetry>"
                }
                """,
            ]
        )

        with patch("data_analysis_agent.agent_runner.load_runtime_config", return_value=runtime_config), patch(
            "data_analysis_agent.agent_runner.build_llm", return_value=llm
        ), patch(
            "data_analysis_agent.agent_runner.build_tool_registry",
            return_value=StubRegistry(cleaned_data_path=None, include_tavily=False),
        ), patch("data_analysis_agent.agent_runner.ingest_input_document") as ingest_mock:
            normalized_csv = tmp_path / "outputs" / "run_20260315_153022" / "data" / "extracted_tables" / "table_02.csv"
            normalized_csv.parent.mkdir(parents=True, exist_ok=True)
            normalized_csv.write_text("x,y\n1,2\n", encoding="utf-8")
            parsed_document = tmp_path / "outputs" / "run_20260315_153022" / "data" / "parsed_document.json"
            parsed_document.parent.mkdir(parents=True, exist_ok=True)
            parsed_document.write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")
            ingest_mock.return_value = IngestionResult(
                input_kind="pdf",
                status="completed",
                summary="PDF 文档解析完成。",
                normalized_data_path=normalized_csv,
                duration_ms=900,
                log_path=tmp_path / "outputs" / "run_20260315_153022" / "logs" / "document_ingestion.json",
                parsed_document_path=parsed_document,
                selected_table_id="table_02",
                candidate_table_count=2,
                selected_table_shape=(7, 5),
                selected_table_headers=("model", "precision"),
                selected_table_numeric_columns=("precision",),
            )

            result = run_analysis(
                pdf_path,
                output_dir=tmp_path / "outputs",
                quality_mode="draft",
                document_ingestion_mode="text_only",
                selected_table_id="table_02",
            )

        self.assertEqual(result.selected_table_id, "table_02")
        self.assertEqual(result.candidate_table_count, 2)
        self.assertEqual(ingest_mock.call_args.kwargs["selected_table_id"], "table_02")


if __name__ == "__main__":
    unittest.main()
