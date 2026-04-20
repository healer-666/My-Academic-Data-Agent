from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.data_context import DataContextSummary
from data_analysis_agent.harness import (
    aggregate_baseline_snapshot,
    build_eval_run_summary,
    build_run_summary_payload,
    compare_baselines,
    load_baseline_snapshot,
    load_regression_rules,
    load_task_spec,
    render_comparison_markdown,
    save_baseline_snapshot,
)
from data_analysis_agent.reporting import ReportTelemetry
from data_analysis_agent.runtime_models import AnalysisRunResult


class HarnessTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"harness_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _build_result(self, run_dir: Path, *, accepted: bool = True, with_figure: bool = True) -> AnalysisRunResult:
        data_dir = run_dir / "data"
        figures_dir = run_dir / "figures"
        logs_dir = run_dir / "logs"
        data_dir.mkdir(parents=True, exist_ok=True)
        figures_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / "final_report.md"
        report_path.write_text("# Report", encoding="utf-8")
        trace_path = logs_dir / "agent_trace.json"
        trace_path.write_text("{}", encoding="utf-8")
        cleaned_data_path = data_dir / "cleaned_data.csv"
        cleaned_data_path.write_text("x\n1\n", encoding="utf-8")
        figure_paths = ()
        if with_figure:
            chart_path = figures_dir / "chart.png"
            chart_path.write_text("fake", encoding="utf-8")
            figure_paths = (chart_path.as_posix(),)
        data_context = DataContextSummary(
            data_path=Path("data/eval/demo.csv"),
            absolute_path=(PROJECT_ROOT / "data" / "eval" / "demo.csv"),
            columns=["x", "y"],
            dtypes="x int64\ny int64",
            shape=(6, 2),
            head_markdown="| x | y |",
            sample_size_warning="",
            small_sample_warning=False,
            context_text="demo context",
        )
        return AnalysisRunResult(
            data_context=data_context,
            raw_result="# Report",
            report_markdown="# Report",
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
                methods=("descriptive_statistics",),
                domain="demo",
                tools_used=("PythonInterpreterTool",),
                search_used=False,
                search_notes="",
                cleaned_data_saved=True,
                cleaned_data_path=cleaned_data_path.as_posix(),
                figures_generated=figure_paths,
                valid=True,
                raw_payload={},
            ),
            methods_used=("descriptive_statistics",),
            detected_domain="demo",
            tools_used=("PythonInterpreterTool",),
            search_status="not_used",
            search_notes="",
            workflow_complete=True,
            workflow_warnings=(),
            missing_artifacts=(),
            quality_mode="standard",
            review_enabled=True,
            review_status="accepted" if accepted else "max_reviews_reached",
            review_rounds_used=1,
            review_critique="Looks good." if accepted else "Chart needs improvement.",
            review_log_paths=(),
            rag_enabled=False,
            rag_status="disabled",
            memory_enabled=False,
            memory_scope_key="eval-demo",
            total_duration_ms=4200,
            execution_audit_status="passed" if accepted else "failed",
            execution_audit_passed=accepted,
            execution_audit_findings=() if accepted else ("No later Python step explicitly reloaded cleaned_data.csv.",),
        )

    def test_load_task_spec_accepts_json_style_yaml(self):
        task = load_task_spec(PROJECT_ROOT / "eval" / "tasks" / "group_comparison_demo.yaml", project_root=PROJECT_ROOT)
        self.assertEqual(task.task_id, "group_comparison_demo")
        self.assertTrue(task.resolved_data_path.name.endswith(".csv"))
        self.assertIn("must_pass_execution_audit", task.key_checks)

    def test_build_eval_run_summary_and_run_summary_payload(self):
        run_dir = self._workspace_case_dir() / "outputs" / "run_demo"
        result = self._build_result(run_dir)
        task = load_task_spec(PROJECT_ROOT / "eval" / "tasks" / "group_comparison_demo.yaml", project_root=PROJECT_ROOT)

        summary = build_eval_run_summary(task, result)
        payload = build_run_summary_payload(result)

        self.assertTrue(summary.accepted)
        self.assertTrue(summary.key_check_results["must_generate_report"])
        self.assertTrue(summary.key_check_results["must_generate_trace"])
        self.assertEqual(payload["primary_failure_type"], "none")
        self.assertEqual(payload["figure_count"], 1)

    def test_baseline_aggregate_save_load_and_compare(self):
        run_dir = self._workspace_case_dir() / "outputs" / "run_demo"
        accepted_result = self._build_result(run_dir / "accepted", accepted=True)
        failed_result = self._build_result(run_dir / "failed", accepted=False, with_figure=False)
        task = load_task_spec(PROJECT_ROOT / "eval" / "tasks" / "group_comparison_demo.yaml", project_root=PROJECT_ROOT)

        current_summary = build_eval_run_summary(task, accepted_result)
        baseline_summary = build_eval_run_summary(task, failed_result)
        current = aggregate_baseline_snapshot(baseline_name="current", summaries=(current_summary,))
        baseline = aggregate_baseline_snapshot(baseline_name="baseline", summaries=(baseline_summary,))

        baseline_path = self._workspace_case_dir() / "baseline.json"
        save_baseline_snapshot(current, baseline_path)
        loaded = load_baseline_snapshot(baseline_path)
        rules = load_regression_rules(PROJECT_ROOT / "eval" / "regression_rules.json")
        comparison = compare_baselines(current=loaded, baseline=baseline, rules=rules)
        markdown = render_comparison_markdown(comparison)

        self.assertEqual(loaded.baseline_name, "current")
        self.assertTrue(comparison["passed"])
        self.assertIn("Harness Baseline Comparison", markdown)


if __name__ == "__main__":
    unittest.main()
