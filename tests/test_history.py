from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.web.history import build_history_choices, load_history_record, scan_run_history


class HistoryTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"history_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _create_run_dir(
        self,
        root: Path,
        name: str,
        *,
        timestamp: str | None = None,
        with_trace: bool = True,
    ) -> Path:
        run_dir = root / name
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
        (run_dir / "data").mkdir(parents=True, exist_ok=True)
        (run_dir / "figures" / "review_round_1").mkdir(parents=True, exist_ok=True)
        (run_dir / "data" / "cleaned_data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (run_dir / "figures" / "review_round_1" / "chart.png").write_text("fake-image", encoding="utf-8")
        (run_dir / "logs" / "document_ingestion.json").write_text("{}", encoding="utf-8")
        (run_dir / "final_report.md").write_text(
            "# Report\n\n![图表](outputs/{}/figures/review_round_1/chart.png)".format(name),
            encoding="utf-8",
        )
        if with_trace:
            figure_path = run_dir / "figures" / "review_round_1" / "chart.png"
            payload = {
                "run_metadata": {
                    "timestamp": timestamp or "2026-03-16T10:00:00",
                    "quality_mode": "standard",
                    "latency_mode": "auto",
                    "input_kind": "pdf",
                },
                "document_ingestion": {
                    "input_kind": "pdf",
                    "status": "completed",
                    "summary": "PDF 主表已选定。",
                    "candidate_table_count": 2,
                    "selected_table_id": "table_01",
                    "selected_table_shape": [7, 5],
                    "pdf_multi_table_mode": True,
                    "log_path": (run_dir / "logs" / "document_ingestion.json").resolve().as_posix(),
                },
                "telemetry": {
                    "domain": "finance",
                    "figures_generated": [figure_path.resolve().as_posix()],
                },
                "artifact_validation": {
                    "workflow_complete": True,
                    "warnings": [],
                    "stage_contract_status": "failed",
                    "stage_contract_findings": ["No later Python step explicitly reloaded cleaned_data.csv."],
                    "stage_contract_passed": False,
                },
                "review_status": "accepted",
                "vision_review_history": [
                    {
                        "status": "completed",
                        "summary": "图表布局清晰。",
                    }
                ],
                "step_traces": [
                    {
                        "step_index": 1,
                        "tool_name": "PythonInterpreterTool",
                        "summary": "Local Python execution",
                    }
                ],
            }
            (run_dir / "logs" / "agent_trace.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return run_dir

    def test_scan_run_history_sorts_newest_first(self):
        case_dir = self._workspace_case_dir()
        self._create_run_dir(case_dir, "run_20260316_090000", timestamp="2026-03-16T09:00:00")
        self._create_run_dir(case_dir, "run_20260316_110000", timestamp="2026-03-16T11:00:00")

        entries = scan_run_history(case_dir)

        self.assertEqual(entries[0].run_dir.name, "run_20260316_110000")
        self.assertEqual(entries[1].run_dir.name, "run_20260316_090000")

    def test_scan_run_history_falls_back_when_trace_missing(self):
        case_dir = self._workspace_case_dir()
        self._create_run_dir(case_dir, "run_20260316_120000", with_trace=False)

        entries = scan_run_history(case_dir)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].report_path.name, "final_report.md")
        self.assertIsNone(entries[0].trace_path)

    def test_build_history_choices_and_load_record_support_empty_state(self):
        case_dir = self._workspace_case_dir()

        choices, selected = build_history_choices(case_dir)
        details = load_history_record(selected, outputs_root=case_dir)

        self.assertEqual(choices, [])
        self.assertIsNone(selected)
        self.assertIn("当前还没有可浏览的历史运行记录", details[0])

    def test_load_history_record_normalizes_relative_report_images_and_shows_table_metadata(self):
        case_dir = self._workspace_case_dir()
        run_dir = self._create_run_dir(case_dir, "run_20260316_130000", timestamp="2026-03-16T13:00:00")

        details = load_history_record(run_dir.as_posix(), outputs_root=case_dir)

        self.assertIn("/file=", details[1])
        self.assertIn("chart.png", details[1])
        self.assertEqual(len(details[2]), 1)
        self.assertIn("候选表数量", details[0])
        self.assertIn("table_01", details[0])
        self.assertIn("PDF 多表综合", details[0])
        self.assertIn("阶段审计", details[0])
        self.assertIn("文档解析日志", details[3])
        self.assertIn("No later Python step explicitly reloaded cleaned_data.csv.", details[3])
        self.assertTrue(str(details[4]).endswith("final_report.md"))
        self.assertTrue(str(details[5]).endswith("agent_trace.json"))
        self.assertTrue(str(details[6]).endswith("cleaned_data.csv"))


if __name__ == "__main__":
    unittest.main()
