from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.agent_runner import run_analysis  # noqa: E402
from data_analysis_agent.harness import (  # noqa: E402
    aggregate_baseline_snapshot,
    build_eval_run_summary,
    load_task_specs,
    save_baseline_snapshot,
)

TASK_EXECUTION_ORDER = (
    "two_group_small_sample",
    "missing_values_by_group",
    "time_series_trend_clean",
    "outlier_sensitive_measurement",
    "correlation_without_causality",
    "multi_group_with_variance_shift",
    "before_after_paired_measure",
    "mixed_units_and_dirty_headers",
    "reference_guideline_lookup",
    "memory_constrained_repeat_task",
)


TASK_SPECIFIC_HINTS = {
    "two_group_small_sample": (
        "Treat this as a small-sample two-group comparison and explicitly warn about sample-size limits.",
        "Do not turn an observed group difference into a causal claim.",
        "If you use a boxplot, explain the median, interquartile spread, group separation, and whether any visible outliers appear.",
        "If you use bars with error bars, explain what the bars summarize and what the error bars represent.",
        "If you use Mann-Whitney U, state the null hypothesis in plain language before interpreting the result.",
    ),
    "missing_values_by_group": (
        "Describe the missing-value pattern before formal analysis and state the exact cleaning rule used.",
        "Make sure the report explains how missingness affects confidence in the findings.",
    ),
    "time_series_trend_clean": (
        "Respect temporal order in both methods and charts.",
        "Do not claim a mechanism or intervention effect beyond the observed trend in the table.",
        "Include this explicit boundary sentence: This report describes an observed trend only and does not establish a mechanism or intervention effect.",
    ),
    "outlier_sensitive_measurement": (
        "Check for outliers explicitly and state whether they were retained, excluded, or only flagged.",
        "Explain whether the conclusion is sensitive to the extreme value.",
    ),
    "correlation_without_causality": (
        "Use correlation language only; do not write the result as causation.",
        "Explain the visible cohort pattern, but keep the interpretation descriptive.",
        "If you use Kruskal-Wallis to compare cohorts, explicitly state in plain language that the null hypothesis is that cohort distributions do not differ systematically.",
    ),
    "multi_group_with_variance_shift": (
        "Compare both central tendency and spread; do not focus on mean difference alone.",
        "If pairwise comparisons are used, state the correction method explicitly.",
    ),
    "before_after_paired_measure": (
        "State clearly that this is paired or repeated-measures data from the same subjects.",
        "Use a paired-data method and explain the within-subject change instead of treating rows as independent groups.",
    ),
    "mixed_units_and_dirty_headers": (
        "Normalize malformed headers and inconsistent naming first, then use the cleaned names consistently in the report.",
        "Do not finish unless the later analysis step clearly reloads the canonical cleaned_data.csv path.",
    ),
    "reference_guideline_lookup": (
        "Use the supplied local reference material when explaining the marker meaning.",
        "Any knowledge-based interpretation must include a matching inline citation from the retrieved evidence register.",
    ),
    "memory_constrained_repeat_task": (
        "If historical memory is retrieved, keep the final wording conservative and consistent with the retrieved guardrails.",
        "Do not overstate effectiveness even if the intervention group looks better.",
    ),
}


def _sort_tasks(tasks):
    order_index = {task_id: index for index, task_id in enumerate(TASK_EXECUTION_ORDER)}
    return tuple(sorted(tasks, key=lambda item: (order_index.get(item.task_id, 999), item.task_id)))


def _build_eval_query(task) -> str:
    lines = [str(task.question).strip()]
    preferred_methods = [item.strip() for item in task.expected_methods if str(item).strip()]
    manual_expectations = [item.strip() for item in task.manual_expectations if str(item).strip()]
    task_hints = list(TASK_SPECIFIC_HINTS.get(task.task_id, ()))

    if preferred_methods:
        lines.append(
            "Harness preferred methods:\n- " + "\n- ".join(preferred_methods)
        )
    if manual_expectations:
        lines.append(
            "Harness task expectations:\n- " + "\n- ".join(manual_expectations)
        )
    if task_hints:
        lines.append(
            "Harness task-specific guardrails:\n- " + "\n- ".join(task_hints)
        )

    lines.append(
        "Harness finish checklist:\n"
        "- Stage 1 must save the canonical cleaned_data.csv path.\n"
        "- A later Python step must explicitly reload that canonical cleaned_data.csv before formal analysis.\n"
        "- Every cited figure must be followed by direct interpretation in the report; do not end with bare image references.\n"
        "- The report must state key limitations, avoid unsupported causal language, and match the actual data structure."
    )
    lines.append(
        "Harness report-writing template:\n"
        "- Write the final report with clearly recognizable sections for Data Overview, Data Cleaning Notes, Methods, Core Statistical Results, Figure Interpretation, Limitations, and Conclusion.\n"
        "- If the task is paired / before-after, say so explicitly in Methods and Results.\n"
        "- If the task contains missing values or outliers, state the handling strategy explicitly in Data Cleaning Notes and again in Limitations when relevant."
    )
    return "\n\n".join(part for part in lines if part).strip()


def _write_aggregate_report(report_dir: Path, summaries) -> Path:
    aggregate_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task_count": len(summaries),
        "summaries": [item.to_dict() for item in summaries],
    }
    target = report_dir / "eval_run_report.json"
    target.write_text(
        json.dumps(aggregate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local eval tasks for the Academic-Data-Agent harness.")
    parser.add_argument("--tasks", default="eval/tasks/*.yaml", help="Glob for task spec files.")
    parser.add_argument("--baseline-name", default=None, help="Optional baseline name to persist under eval/baselines.")
    parser.add_argument("--output-root", default="outputs", help="Run artifact root passed to run_analysis.")
    parser.add_argument("--reports-dir", default="eval/reports", help="Directory for harness run outputs.")
    parser.add_argument("--env-file", default=None, help="Optional .env file path.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    tasks = _sort_tasks(load_task_specs(args.tasks, project_root=PROJECT_ROOT))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = (PROJECT_ROOT / args.reports_dir / timestamp).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    print(f"Eval report directory: {report_dir.as_posix()}", flush=True)

    summaries = []
    total_tasks = len(tasks)
    for index, task in enumerate(tasks, start=1):
        started_at = perf_counter()
        print(
            f"[{index}/{total_tasks}] Starting {task.task_id} | rag={task.use_rag} | memory={task.use_memory}",
            flush=True,
        )
        try:
            result = run_analysis(
                task.resolved_data_path,
                query=_build_eval_query(task),
                output_dir=PROJECT_ROOT / args.output_root,
                env_file=args.env_file,
                quality_mode=task.quality_mode,
                latency_mode=task.latency_mode,
                use_rag=task.use_rag,
                knowledge_paths=task.resolved_knowledge_paths,
                use_memory=task.use_memory,
                memory_scope_key=task.memory_scope_key,
                task_type=task.task_type,
                task_expectations=task.manual_expectations,
            )
        except KeyboardInterrupt:
            _write_aggregate_report(report_dir, summaries)
            print(
                f"\nInterrupted during {task.task_id}. Partial report saved to {report_dir.as_posix()}",
                flush=True,
            )
            raise
        except Exception as exc:
            _write_aggregate_report(report_dir, summaries)
            error_path = report_dir / f"{task.task_id}__error.json"
            error_path.write_text(
                json.dumps(
                    {
                        "task_id": task.task_id,
                        "title": task.title,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(
                f"[{index}/{total_tasks}] Failed {task.task_id} after {perf_counter() - started_at:.1f}s | {exc}",
                flush=True,
            )
            raise
        summary = build_eval_run_summary(task, result)
        summaries.append(summary)
        summary_path = report_dir / f"{task.task_id}__{result.run_dir.name}.json"
        summary_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        _write_aggregate_report(report_dir, summaries)
        print(
            f"[{index}/{total_tasks}] Finished {task.task_id} | accepted={summary.accepted} | "
            f"review={summary.review_status} | audit={summary.execution_audit_status} | "
            f"duration={summary.duration_seconds:.1f}s",
            flush=True,
        )

    if args.baseline_name:
        snapshot = aggregate_baseline_snapshot(
            baseline_name=args.baseline_name,
            summaries=tuple(summaries),
        )
        baseline_path = PROJECT_ROOT / "eval" / "baselines" / f"{args.baseline_name}.json"
        save_baseline_snapshot(snapshot, baseline_path)
        print(f"Saved baseline: {baseline_path.as_posix()}")

    print(f"Executed tasks: {len(summaries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
