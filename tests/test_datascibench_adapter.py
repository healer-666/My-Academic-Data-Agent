from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_PATH = PROJECT_ROOT / "eval" / "scripts"
if str(SCRIPTS_PATH) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PATH))

import run_datascibench  # noqa: E402


class DataSciBenchAdapterTests(unittest.TestCase):
    def _case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"datascibench_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _write_fake_datascibench(self, root: Path) -> None:
        tasks = [
            ("csv_excel_1", "1 = embedded data", "Summarize the embedded table and save result.csv."),
            ("csv_excel_2", "1", "Compute the mean from the values in the prompt."),
            ("deep_learning_1", "2", "Train a neural network with external images."),
        ]
        index_items = []
        for task_id, data_source_type, prompt in tasks:
            prompt_path = Path("data") / task_id / "prompt.json"
            full_path = root / prompt_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(
                json.dumps(
                    {
                        "prompt": prompt,
                        "data_source_type": data_source_type,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            index_items.append({"task_id": task_id, "prompt_path": prompt_path.as_posix()})
        (root / "task_index.json").write_text(
            json.dumps({"source": "fake", "tasks": index_items}, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_load_select_and_query(self):
        root = self._case_dir() / "datascibench"
        self._write_fake_datascibench(root)

        tasks = run_datascibench.load_datascibench_tasks(root, allow_download=False)
        selected = run_datascibench.select_datascibench_tasks(
            tasks,
            sample_size=10,
            seed=20260511,
            data_source_type="1",
            task_group="csv_excel",
        )
        query = run_datascibench.build_datascibench_query(selected[0])

        self.assertEqual(len(tasks), 3)
        self.assertEqual([task.task_id for task in selected], ["csv_excel_1", "csv_excel_2"])
        self.assertIn("DataSciBench task", query)
        self.assertIn("<datascibench_result>", query)
        self.assertNotIn("Harness task-specific guardrails", query)

    def test_select_all_filters(self):
        root = self._case_dir() / "datascibench"
        self._write_fake_datascibench(root)

        tasks = run_datascibench.load_datascibench_tasks(root, allow_download=False)
        selected = run_datascibench.select_datascibench_tasks(
            tasks,
            sample_size=10,
            seed=20260511,
            data_source_type="all",
            task_group="all",
        )

        self.assertEqual([task.task_id for task in selected], ["csv_excel_1", "csv_excel_2", "deep_learning_1"])

    def test_extract_datascibench_result_block(self):
        compliant, text, source = run_datascibench.extract_datascibench_result_block(
            "# Report\n\n<datascibench_result>\ncreated result.csv\n</datascibench_result>"
        )

        self.assertTrue(compliant)
        self.assertEqual(text, "created result.csv")
        self.assertEqual(source, "block")

    def test_extract_datascibench_result_falls_back_to_report(self):
        compliant, text, source = run_datascibench.extract_datascibench_result_block("# Report\n\nCompleted.")

        self.assertTrue(compliant)
        self.assertIn("Completed", text)
        self.assertEqual(source, "report_fallback")

    def test_run_datascibench_sample_with_mock_runner(self):
        case_dir = self._case_dir()
        root = case_dir / "datascibench"
        self._write_fake_datascibench(root)

        def fake_runner(data_path, **kwargs):
            self.assertTrue(Path(data_path).exists())
            self.assertEqual(kwargs["task_type"], "datascibench")
            self.assertFalse(kwargs["use_rag"])
            self.assertFalse(kwargs["use_memory"])
            self.assertEqual(kwargs["quality_mode"], "draft")
            self.assertIn("<datascibench_result>", kwargs["query"])
            return SimpleNamespace(
                report_markdown="# Report\n\n<datascibench_result>\ncreated result.csv\n</datascibench_result>\n",
                workflow_complete=True,
                execution_audit_passed=True,
                trace_path=case_dir / "trace.json",
                run_dir=case_dir / "run",
            )

        config = run_datascibench.DataSciBenchRunConfig(
            data_root=root,
            reports_dir=case_dir / "reports",
            output_root=case_dir / "outputs",
            sample_size=2,
            seed=20260511,
            allow_download=False,
            data_source_type="1",
            task_group="csv_excel",
        )

        result = run_datascibench.run_datascibench_sample(config, runner=fake_runner)
        summary = result["summary"]
        responses_path = Path(result["responses_path"])

        self.assertEqual(summary["sample_size"], 2)
        self.assertEqual(summary["completed_rate"], 1.0)
        self.assertEqual(summary["unsupported_count"], 2)
        self.assertEqual(summary["run_error_count"], 0)
        self.assertEqual(summary["format_failure_count"], 0)
        self.assertTrue(Path(result["summary_path"]).exists())
        self.assertTrue(Path(result["summary_markdown_path"]).exists())
        self.assertTrue(Path(result["failure_review_path"]).exists())
        self.assertTrue(Path(result["progress_log_path"]).exists())
        self.assertEqual(len(responses_path.read_text(encoding="utf-8").splitlines()), 2)
        for record in summary["results"]:
            self.assertTrue(record["format_compliant"])
            self.assertTrue(Path(record["raw_report_path"]).exists())


if __name__ == "__main__":
    unittest.main()
