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

import run_dabench  # noqa: E402


class DABenchAdapterTests(unittest.TestCase):
    def _case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"dabench_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _write_fake_dabench(self, root: Path) -> None:
        data_dir = root / "data"
        tables_dir = data_dir / "da-dev-tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        questions = [
            {
                "id": 1,
                "question": "What is the mean value?",
                "constraints": "Use the value column.",
                "format": "@mean_value[answer]",
                "file_name": "table_a.csv",
                "level": "easy",
            },
            {
                "id": 2,
                "question": "What is the max score?",
                "constraints": "Use the score column.",
                "format": "@max_score[answer]",
                "file_name": "table_b.csv",
                "level": "hard",
            },
        ]
        labels = [
            {"id": 1, "common_answers": [["mean_value", "2.00"]]},
            {"id": 2, "common_answers": [["max_score", 9]]},
        ]
        (data_dir / "da-dev-questions.jsonl").write_text(
            "\n".join(json.dumps(item) for item in questions) + "\n",
            encoding="utf-8",
        )
        (data_dir / "da-dev-labels.jsonl").write_text(
            "\n".join(json.dumps(item) for item in labels) + "\n",
            encoding="utf-8",
        )
        (tables_dir / "table_a.csv").write_text("value\n1\n2\n3\n", encoding="utf-8")
        (tables_dir / "table_b.csv").write_text("score\n7\n9\n", encoding="utf-8")

    def test_load_sample_and_query(self):
        root = self._case_dir() / "dabench"
        self._write_fake_dabench(root)

        tasks = run_dabench.load_dabench_tasks(root, allow_download=False)
        selected = run_dabench.sample_dabench_tasks(tasks, sample_size=1, seed=20260510)
        query = run_dabench.build_dabench_query(tasks[0], dabench_mode=True)

        self.assertEqual(len(tasks), 2)
        self.assertEqual(len(selected), 1)
        self.assertIn("What is the mean value?", query)
        self.assertIn("<dabench_answer>", query)
        self.assertIn("prioritize the DABench answer block", query)
        self.assertNotIn("Harness task-specific guardrails", query)

    def test_extract_and_score_answer_block(self):
        report = (
            "# Report\n\n"
            "<dabench_answer>\n"
            "@mean_value[2.0]\n"
            "@label[Control]\n"
            "</dabench_answer>\n"
        )

        extracted = run_dabench.extract_dabench_answer(report, ("mean_value", "label"))
        evaluation = run_dabench.evaluate_dabench_prediction(
            extracted.answer_text,
            (("mean_value", "2.00"), ("label", "control")),
        )

        self.assertTrue(extracted.format_compliant)
        self.assertEqual(extracted.source, "block")
        self.assertTrue(evaluation["exact_match"])
        self.assertEqual(evaluation["per_metric"], {"mean_value": True, "label": True})

    def test_run_dabench_sample_with_mock_runner(self):
        case_dir = self._case_dir()
        root = case_dir / "dabench"
        self._write_fake_dabench(root)

        def fake_runner(data_path, **kwargs):
            self.assertTrue(Path(data_path).exists())
            self.assertFalse(kwargs["use_rag"])
            self.assertFalse(kwargs["use_memory"])
            self.assertEqual(kwargs["vision_review_mode"], "off")
            self.assertEqual(kwargs["quality_mode"], "draft")
            self.assertEqual(kwargs["latency_mode"], "quality")
            expected_max_steps = 12 if Path(data_path).name == "table_a.csv" else 20
            self.assertEqual(kwargs["max_steps"], expected_max_steps)
            task_answer = "@mean_value[2.00]" if Path(data_path).name == "table_a.csv" else "@max_score[9]"
            return SimpleNamespace(
                report_markdown=f"# Report\n\n<dabench_answer>\n{task_answer}\n</dabench_answer>\n",
                workflow_complete=False,
                execution_audit_passed=False,
                review_status="skipped",
                trace_path=case_dir / "trace.json",
                run_dir=case_dir / "run",
            )

        config = run_dabench.DABenchRunConfig(
            data_root=root,
            reports_dir=case_dir / "reports",
            output_root=case_dir / "outputs",
            sample_size=2,
            seed=20260510,
            allow_download=False,
            max_steps=12,
            quality_mode="draft",
            latency_mode="quality",
            vision_review_mode="off",
            dabench_mode=True,
        )

        result = run_dabench.run_dabench_sample(config, runner=fake_runner)
        summary = result["summary"]
        responses_path = Path(result["responses_path"])

        self.assertEqual(summary["sample_size"], 2)
        self.assertEqual(summary["exact_match_count"], 2)
        self.assertEqual(summary["exact_match_rate"], 1.0)
        self.assertEqual(summary["benchmark_pass_rate"], 1.0)
        self.assertEqual(summary["strict_project_pass_rate"], 0.0)
        self.assertEqual(summary["format_compliance_rate"], 1.0)
        self.assertTrue(Path(result["summary_path"]).exists())
        self.assertTrue(Path(result["summary_markdown_path"]).exists())
        self.assertTrue(Path(result["failure_review_path"]).exists())
        self.assertTrue(Path(result["progress_log_path"]).exists())
        self.assertTrue(Path(result["run_config_path"]).exists())
        self.assertEqual(len(responses_path.read_text(encoding="utf-8").splitlines()), 2)
        self.assertIn("benchmark_pass_rate", Path(result["summary_markdown_path"]).read_text(encoding="utf-8"))
        for record in summary["results"]:
            self.assertTrue(Path(record["raw_report_path"]).exists())
            self.assertEqual(record["failure_type"], "none")
            self.assertIn(record["level"], {"easy", "hard"})


if __name__ == "__main__":
    unittest.main()
