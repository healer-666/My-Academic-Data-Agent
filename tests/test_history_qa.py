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

from data_analysis_agent.history_qa import answer_history_question, index_completed_runs, retrieve_history_context


class HistoryQaTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"history_qa_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _create_run_dir(
        self,
        root: Path,
        name: str,
        *,
        review_status: str = "accepted",
        workflow_complete: bool = True,
        with_trace: bool = True,
    ) -> Path:
        run_dir = root / name
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
        (run_dir / "data").mkdir(parents=True, exist_ok=True)
        (run_dir / "figures").mkdir(parents=True, exist_ok=True)
        (run_dir / "data" / "cleaned_data.csv").write_text("marker,value\nA,1\n", encoding="utf-8")
        (run_dir / "final_report.md").write_text(
            "# Report\n\n## Result Interpretation\nBiomarker A increases in the treatment group.\n\n![Trend](figures/chart.png)\n",
            encoding="utf-8",
        )
        (run_dir / "figures" / "chart.png").write_text("fake-image", encoding="utf-8")
        if with_trace:
            payload = {
                "run_metadata": {
                    "timestamp": "2026-04-14T10:00:00",
                    "quality_mode": "standard",
                    "latency_mode": "auto",
                    "input_kind": "tabular",
                    "data_path": (run_dir / "data" / "cleaned_data.csv").as_posix(),
                    "memory_scope_key": "project-alpha",
                },
                "telemetry": {
                    "domain": "biomedicine",
                    "methods": ["Mann-Whitney U"],
                    "figures_generated": [(run_dir / "figures" / "chart.png").resolve().as_posix()],
                },
                "artifact_validation": {
                    "workflow_complete": workflow_complete,
                    "warnings": [],
                },
                "review_status": review_status,
                "review_history": [
                    {"decision": review_status, "critique": "Keep the interpretation conservative."},
                ],
                "step_traces": [
                    {"step_index": 1, "tool_name": "PythonInterpreterTool", "summary": "Computed non-parametric test."},
                ],
                "memory": {
                    "retrieved_records": [
                        {"memory_type": "analysis_summary", "text_excerpt": "Avoid causal language."},
                    ],
                },
                "success_memory": {
                    "retrieved_records": [
                        {"memory_type": "analysis_summary", "text_excerpt": "Keep interpretation conservative."},
                    ],
                },
                "failure_memory": {
                    "retrieved_records": [
                        {
                            "failure_type": "failure_constraint",
                            "text_excerpt": "Do not finish before reloading cleaned_data.csv in Stage 2.",
                        },
                    ],
                },
            }
            (run_dir / "logs" / "agent_trace.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return run_dir

    def test_index_completed_runs_only_includes_completed_run_directories(self):
        case_dir = self._workspace_case_dir()
        self._create_run_dir(case_dir, "run_20260414_100000", with_trace=True)
        self._create_run_dir(case_dir, "run_20260414_110000", with_trace=False)
        (case_dir / "web_uploads").mkdir(parents=True, exist_ok=True)

        records = index_completed_runs(case_dir)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].run_id, "run_20260414_100000")
        self.assertEqual(records[0].methods_used, ("Mann-Whitney U",))
        self.assertIn("Keep interpretation conservative", records[0].success_memory_snippets[0])
        self.assertIn("Do not finish before reloading cleaned_data.csv", records[0].failure_memory_snippets[0])

    def test_retrieve_history_context_supports_single_run_filter(self):
        case_dir = self._workspace_case_dir()
        self._create_run_dir(case_dir, "run_20260414_100000", review_status="accepted")
        self._create_run_dir(case_dir, "run_20260414_120000", review_status="rejected")

        retrieval = retrieve_history_context(
            "为什么使用非参数检验？",
            run_ids=["run_20260414_100000"],
            mode="single",
            outputs_root=case_dir,
        )

        self.assertEqual(retrieval.mode, "single")
        self.assertEqual(retrieval.selected_run_ids, ("run_20260414_100000",))
        self.assertTrue(all(item.run_id == "run_20260414_100000" for item in retrieval.slices))
        self.assertTrue(any(item.source_type == "failure_memory" for item in retrieval.slices))

    def test_answer_history_question_falls_back_and_marks_sources(self):
        case_dir = self._workspace_case_dir()
        self._create_run_dir(case_dir, "run_20260414_100000", review_status="rejected")

        with patch("data_analysis_agent.history_qa.load_runtime_config", side_effect=RuntimeError("no llm")):
            answer = answer_history_question(
                "哪次报告被拒绝，原因是什么？",
                run_ids=["run_20260414_100000"],
                mode="compare",
                outputs_root=case_dir,
            )

        self.assertIn("run_20260414_100000", answer.answer_markdown)
        self.assertIn("review_status=rejected", answer.answer_markdown)
        self.assertTrue(answer.warnings)
        self.assertTrue(any("run_20260414_100000" in item for item in answer.sources))


if __name__ == "__main__":
    unittest.main()
