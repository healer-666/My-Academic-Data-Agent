from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_PATH = PROJECT_ROOT / "eval" / "scripts"
if str(SCRIPTS_PATH) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PATH))

import prepare_datascibench_official_eval as official_eval  # noqa: E402


class DataSciBenchOfficialEvalTests(unittest.TestCase):
    def _case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"datascibench_official_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def test_extract_task_func_code_from_trace(self):
        case_dir = self._case_dir()
        trace_path = case_dir / "agent_trace.json"
        trace_path.write_text(
            json.dumps(
                {
                    "steps": [
                        {
                            "tool_input": (
                                "import numpy as np\n"
                                "print('setup')\n"
                                "def task_func(data, value):\n"
                                "    arr = np.array(data)\n"
                                "    return arr[arr > value], int(np.sum(arr > value))\n"
                                "print(task_func([1, 2], 1))\n"
                            )
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        code = official_eval.extract_task_func_code(trace_path)

        self.assertIn("import numpy as np", code)
        self.assertIn("def task_func", code)
        self.assertIn("return", code)
        self.assertNotIn("print('setup')", code)

    def test_stage_bcb_output_writes_official_jsonl(self):
        case_dir = self._case_dir()
        official_root = case_dir / "official"
        (official_root / "data" / "bcb1").mkdir(parents=True)
        trace_path = case_dir / "trace.json"
        trace_path.write_text(
            json.dumps({"tool_input": "import numpy as np\ndef task_func(data, value):\n    return np.array(data), 0\n"}),
            encoding="utf-8",
        )
        record = {
            "id": "bcb1",
            "task_group": "bcb",
            "trace_path": trace_path.as_posix(),
            "raw_report_path": "",
            "run_dir": (case_dir / "run").as_posix(),
            "duration_seconds": 1.0,
        }
        config = official_eval.OfficialEvalConfig(
            summary_path=case_dir / "summary.json",
            official_root=official_root,
            reports_dir=case_dir / "reports",
        )

        staged = official_eval.stage_bcb_output(record, config)
        output_path = Path(staged["official_input_path"])
        rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(staged["official_prepare_status"], "prepared")
        self.assertEqual(len(rows), 1)
        self.assertIn("def task_func", rows[0]["plan"][0]["code"])

    def test_stage_regular_output_copies_metric_artifact_and_marks_gt(self):
        case_dir = self._case_dir()
        official_root = case_dir / "official"
        task_dir = official_root / "data" / "csv_excel_1"
        metric_dir = official_root / "metric" / "csv_excel_1"
        task_dir.mkdir(parents=True)
        (task_dir / "gt").mkdir()
        metric_dir.mkdir(parents=True)
        (metric_dir / "metric.yaml").write_text(
            "TMC-list:\n- code: \"output = pd.read_excel('target.xlsx')\"\n  ground_truth: target.xlsx\n",
            encoding="utf-8",
        )
        run_dir = case_dir / "run"
        run_dir.mkdir()
        (run_dir / "agent_trace.json").write_text("{}", encoding="utf-8")
        raw_report = case_dir / "final.md"
        raw_report.write_text(f"Updated target: `{(case_dir / 'target.xlsx').as_posix()}`", encoding="utf-8")
        (case_dir / "target.xlsx").write_bytes(b"fake-xlsx")
        record = {
            "id": "csv_excel_1",
            "task_group": "csv_excel",
            "run_dir": run_dir.as_posix(),
            "trace_path": (run_dir / "agent_trace.json").as_posix(),
            "raw_report_path": raw_report.as_posix(),
        }
        config = official_eval.OfficialEvalConfig(
            summary_path=case_dir / "summary.json",
            official_root=official_root,
            reports_dir=case_dir / "reports",
        )

        staged = official_eval.stage_regular_output(record, config)
        official_run_dir = Path(staged["official_input_path"])

        self.assertEqual(staged["official_prepare_status"], "prepared")
        self.assertTrue((official_run_dir / "logs.txt").exists())
        self.assertTrue((official_run_dir / "final_report.md").exists())
        self.assertTrue((official_run_dir / "target.xlsx").exists())


if __name__ == "__main__":
    unittest.main()
