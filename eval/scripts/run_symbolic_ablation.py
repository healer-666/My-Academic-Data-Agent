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
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from data_analysis_agent.agent_runner import run_analysis  # noqa: E402
from data_analysis_agent.harness import (  # noqa: E402
    SYMBOLIC_ABLATION_PROFILES,
    build_ablation_record,
    build_symbolic_ablation_report,
    load_manual_annotations,
    load_task_specs,
    render_symbolic_ablation_markdown,
)
from run_eval import _build_eval_query, _sort_tasks  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run symbolic-governance ablations for Academic-Data-Agent.")
    parser.add_argument("--tasks", default="eval/tasks/*.yaml", help="Glob for task spec files.")
    parser.add_argument("--output-root", default="outputs", help="Run artifact root passed to run_analysis.")
    parser.add_argument("--reports-dir", default="eval/reports", help="Directory for ablation reports.")
    parser.add_argument("--env-file", default=None, help="Optional .env file path.")
    parser.add_argument("--seed", default="default", help="Seed label recorded for paired comparison.")
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=SYMBOLIC_ABLATION_PROFILES,
        default=list(SYMBOLIC_ABLATION_PROFILES),
        help="Profiles to run. Defaults to full prompt_only none.",
    )
    parser.add_argument(
        "--manual-annotations",
        default=None,
        help="Optional JSON file with semi-manual statistical_validity and causal_language_violation annotations.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    tasks = _sort_tasks(load_task_specs(args.tasks, project_root=PROJECT_ROOT))
    profiles = tuple(args.profiles)
    annotations = load_manual_annotations(args.manual_annotations)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = (PROJECT_ROOT / args.reports_dir / timestamp).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    print(f"Symbolic ablation report directory: {report_dir.as_posix()}", flush=True)

    records: list[dict[str, object]] = []
    total_runs = len(tasks) * len(profiles)
    run_index = 0
    for task in tasks:
        for profile in profiles:
            run_index += 1
            started_at = perf_counter()
            print(
                f"[{run_index}/{total_runs}] Starting {task.task_id} | profile={profile} | "
                f"rag={task.use_rag} | memory={task.use_memory}",
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
                    symbolic_profile=profile,
                )
            except KeyboardInterrupt:
                _write_reports(report_dir, records, timestamp)
                print(f"\nInterrupted. Partial ablation report saved to {report_dir.as_posix()}", flush=True)
                raise
            except Exception as exc:
                _write_reports(report_dir, records, timestamp)
                error_path = report_dir / f"{task.task_id}__{profile}__error.json"
                error_path.write_text(
                    json.dumps(
                        {
                            "task_id": task.task_id,
                            "profile": profile,
                            "seed": args.seed,
                            "error": str(exc),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                print(
                    f"[{run_index}/{total_runs}] Failed {task.task_id} profile={profile} "
                    f"after {perf_counter() - started_at:.1f}s | {exc}",
                    flush=True,
                )
                raise
            record = build_ablation_record(
                task_id=task.task_id,
                seed=args.seed,
                profile=profile,
                result=result,
                manual_annotations=annotations,
            )
            records.append(record)
            _write_reports(report_dir, records, timestamp)
            print(
                f"[{run_index}/{total_runs}] Finished {task.task_id} | profile={profile} | "
                f"workflow={record['workflow_complete']} | audit={record['execution_audit_passed']} | "
                f"contract={record['report_contract_passed']} | duration={record['duration_seconds']}s",
                flush=True,
            )

    print(f"Executed ablation runs: {len(records)}")
    return 0


def _write_reports(report_dir: Path, records: list[dict[str, object]], timestamp: str) -> None:
    report = build_symbolic_ablation_report(records=records, generated_at=timestamp)
    json_path = report_dir / "symbolic_ablation_report.json"
    md_path = report_dir / "symbolic_ablation_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_symbolic_ablation_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

