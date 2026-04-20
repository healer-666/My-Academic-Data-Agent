from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


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
    tasks = load_task_specs(args.tasks, project_root=PROJECT_ROOT)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = (PROJECT_ROOT / args.reports_dir / timestamp).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    for task in tasks:
        result = run_analysis(
            task.resolved_data_path,
            query=task.question,
            output_dir=PROJECT_ROOT / args.output_root,
            env_file=args.env_file,
            quality_mode=task.quality_mode,
            latency_mode=task.latency_mode,
            use_rag=task.use_rag,
            use_memory=task.use_memory,
            memory_scope_key=task.memory_scope_key,
        )
        summary = build_eval_run_summary(task, result)
        summaries.append(summary)
        summary_path = report_dir / f"{task.task_id}__{result.run_dir.name}.json"
        summary_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    aggregate_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task_count": len(summaries),
        "summaries": [item.to_dict() for item in summaries],
    }
    (report_dir / "eval_run_report.json").write_text(
        json.dumps(aggregate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Eval report directory: {report_dir.as_posix()}")

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
