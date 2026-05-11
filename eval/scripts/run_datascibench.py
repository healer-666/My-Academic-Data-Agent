from __future__ import annotations

import argparse
import contextlib
import csv
import json
import random
import re
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.agent_runner import run_analysis  # noqa: E402


GITHUB_API_TREE = "https://api.github.com/repos/THUDM/DataSciBench/git/trees/main?recursive=1"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/THUDM/DataSciBench/main"
HF_DATASET_URL = "https://huggingface.co/datasets/zd21/DataSciBench/tree/main"
DEFAULT_SEED = 20260511
DEFAULT_SAMPLE_SIZE = 10


@dataclass(frozen=True)
class DataSciBenchTask:
    task_id: str
    prompt: str
    data_source_type: str
    task_group: str
    prompt_path: Path
    raw_prompt: dict[str, Any]


@dataclass(frozen=True)
class DataSciBenchRunConfig:
    data_root: Path
    reports_dir: Path
    output_root: Path
    env_file: Path | None = None
    sample_size: int = DEFAULT_SAMPLE_SIZE
    seed: int = DEFAULT_SEED
    task_ids: tuple[str, ...] = ()
    allow_download: bool = True
    data_source_type: str = "1"
    task_group: str = "csv_excel"
    max_steps: int = 12
    quality_mode: str = "draft"
    latency_mode: str = "quality"
    symbolic_profile: str = "full"
    vision_review_mode: str = "off"
    task_retries: int = 0


def _resolve_path(path: str | Path, *, root: Path = PROJECT_ROOT) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _download_text(url: str, *, timeout_seconds: int = 180, attempts: int = 3) -> str:
    request = Request(url, headers={"User-Agent": "Academic-Data-Agent-DataSciBench/1.0"})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(2 * attempt, 5))
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Unable to download {url}")


def _download_file(url: str, target: Path, *, timeout_seconds: int = 180, attempts: int = 3) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_target = target.with_name(f"{target.name}.tmp")
    request = Request(url, headers={"User-Agent": "Academic-Data-Agent-DataSciBench/1.0"})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                with tmp_target.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
            tmp_target.replace(target)
            return
        except Exception as exc:
            last_error = exc
            with contextlib.suppress(OSError):
                tmp_target.unlink()
            if attempt < attempts:
                time.sleep(min(2 * attempt, 5))
    if last_error is not None:
        raise last_error


def _task_group(task_id: str) -> str:
    match = re.match(r"([A-Za-z_]+)", task_id)
    return match.group(1).rstrip("_") if match else "unknown"


def _data_source_code(value: str) -> str:
    return str(value or "").split("=", 1)[0].strip()


def ensure_datascibench_prompts(data_root: Path, *, allow_download: bool = True) -> Path:
    index_path = data_root / "task_index.json"
    if index_path.exists():
        return index_path
    if not allow_download:
        raise FileNotFoundError(f"Missing DataSciBench task index: {index_path.as_posix()}")
    payload = json.loads(_download_text(GITHUB_API_TREE))
    prompt_paths = sorted(
        item["path"]
        for item in payload.get("tree", [])
        if item.get("type") == "blob" and item.get("path", "").startswith("data/") and item.get("path", "").endswith("/prompt.json")
    )
    tasks: list[dict[str, str]] = []
    for path in prompt_paths:
        task_id = Path(path).parent.name
        local_path = data_root / path
        if not local_path.exists():
            raw_url = f"{GITHUB_RAW_BASE}/{quote(path, safe='/')}"
            _download_file(raw_url, local_path)
        tasks.append({"task_id": task_id, "prompt_path": path})
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps({"source": GITHUB_API_TREE, "tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
    return index_path


def load_datascibench_tasks(data_root: Path, *, allow_download: bool = True) -> tuple[DataSciBenchTask, ...]:
    index_path = ensure_datascibench_prompts(data_root, allow_download=allow_download)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    tasks: list[DataSciBenchTask] = []
    for item in index.get("tasks", []):
        task_id = str(item["task_id"])
        prompt_path = data_root / str(item["prompt_path"])
        raw_prompt = json.loads(prompt_path.read_text(encoding="utf-8"))
        prompt = str(raw_prompt.get("prompt", "")).strip()
        data_source_type = str(raw_prompt.get("data_source_type", "")).strip()
        tasks.append(
            DataSciBenchTask(
                task_id=task_id,
                prompt=prompt,
                data_source_type=data_source_type,
                task_group=_task_group(task_id),
                prompt_path=prompt_path,
                raw_prompt=raw_prompt,
            )
        )
    return tuple(sorted(tasks, key=lambda task: task.task_id))


def select_datascibench_tasks(
    tasks: Iterable[DataSciBenchTask],
    *,
    task_ids: Iterable[str] = (),
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
    data_source_type: str = "1",
    task_group: str = "csv_excel",
) -> tuple[DataSciBenchTask, ...]:
    task_list = tuple(tasks)
    explicit_ids = tuple(str(item).strip() for item in task_ids if str(item).strip())
    if explicit_ids:
        by_id = {task.task_id: task for task in task_list}
        missing = [task_id for task_id in explicit_ids if task_id not in by_id]
        if missing:
            raise ValueError(f"Requested DataSciBench task ids do not exist: {', '.join(missing)}")
        return tuple(by_id[task_id] for task_id in explicit_ids)
    data_source_filter = "" if str(data_source_type).strip().lower() in {"", "all", "*"} else str(data_source_type).strip()
    task_group_filter = "" if str(task_group).strip().lower() in {"", "all", "*"} else str(task_group).strip()
    filtered = [
        task
        for task in task_list
        if (not data_source_filter or _data_source_code(task.data_source_type) == data_source_filter)
        and (not task_group_filter or task.task_id.startswith(task_group_filter))
    ]
    if sample_size <= 0 or sample_size >= len(filtered):
        return tuple(filtered)
    rng = random.Random(seed)
    shuffled = list(filtered)
    rng.shuffle(shuffled)
    return tuple(sorted(shuffled[:sample_size], key=lambda task: task.task_id))


def build_datascibench_query(task: DataSciBenchTask) -> str:
    return (
        "Complete this DataSciBench task using Python where appropriate.\n\n"
        "Important benchmark constraints:\n"
        "- The task prompt is authoritative; follow requested file names and outputs when possible.\n"
        "- If the prompt embeds all needed data, use only that embedded data.\n"
        "- Keep the final report concise and include paths of any generated artifacts.\n\n"
        f"Task id: {task.task_id}\n"
        f"Data source type: {task.data_source_type}\n\n"
        f"Prompt:\n{task.prompt}\n\n"
        "<datascibench_result>\nSummarize completed artifacts and any unsupported requirements here.\n</datascibench_result>"
    )


def create_placeholder_dataset(task: DataSciBenchTask, input_root: Path) -> Path:
    input_root.mkdir(parents=True, exist_ok=True)
    target = input_root / f"{task.task_id}.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["task_id", "data_source_type", "prompt_preview"])
        writer.writerow([task.task_id, task.data_source_type, task.prompt[:500]])
    return target


def _append_progress(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def _save_raw_report(report_dir: Path, task_id: str, report_markdown: str) -> Path:
    raw_dir = report_dir / "raw_reports"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{task_id}_final_report.md"
    path.write_text(report_markdown, encoding="utf-8")
    return path


def _official_scoring_status(task: DataSciBenchTask, data_root: Path) -> str:
    gt_dir = data_root / "data" / task.task_id / "gt"
    metric_dir = data_root / "metric" / task.task_id
    if gt_dir.exists() or metric_dir.exists():
        return "unsupported_official_tfc_not_integrated"
    return "unsupported_missing_official_gt"


def extract_datascibench_result_block(report_markdown: str) -> tuple[bool, str, str]:
    match = re.search(
        r"<datascibench_result>\s*(.*?)\s*</datascibench_result>",
        str(report_markdown or ""),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        fallback = str(report_markdown or "").strip()
        return bool(fallback), fallback[:2000], "report_fallback" if fallback else "missing"
    text = match.group(1).strip()
    return bool(text), text, "block"


def build_summary(*, records: list[dict[str, Any]], config: DataSciBenchRunConfig, report_dir: Path) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    scoring_counts: dict[str, int] = {}
    for record in records:
        status_counts[str(record.get("status", "unknown"))] = status_counts.get(str(record.get("status", "unknown")), 0) + 1
        scoring_counts[str(record.get("official_scoring_status", "unknown"))] = scoring_counts.get(
            str(record.get("official_scoring_status", "unknown")),
            0,
        ) + 1
    durations = [float(record.get("duration_seconds", 0.0) or 0.0) for record in records]
    denominator = len(records) or 1
    return {
        "benchmark": "DataSciBench",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sample_size": len(records),
        "requested_sample_size": config.sample_size,
        "seed": config.seed,
        "task_ids": [record.get("id") for record in records],
        "completed_rate": round(sum(1 for record in records if record.get("status") == "completed") / denominator, 4),
        "scored_count": sum(1 for record in records if record.get("official_scoring_status") == "scored"),
        "unsupported_count": sum(1 for record in records if str(record.get("official_scoring_status", "")).startswith("unsupported")),
        "run_error_count": sum(1 for record in records if record.get("status") == "failed"),
        "format_failure_count": sum(1 for record in records if record.get("status") == "completed" and not record.get("format_compliant")),
        "avg_duration_seconds": round(sum(durations) / denominator, 3),
        "status_distribution": status_counts,
        "official_scoring_distribution": scoring_counts,
        "config": {
            **asdict(config),
            "data_root": config.data_root.as_posix(),
            "reports_dir": config.reports_dir.as_posix(),
            "output_root": config.output_root.as_posix(),
            "env_file": config.env_file.as_posix() if config.env_file else None,
        },
        "data_source": {
            "github": "https://github.com/THUDM/DataSciBench",
            "ground_truth": HF_DATASET_URL,
        },
        "report_dir": report_dir.as_posix(),
        "results": records,
    }


def render_failure_review(records: Iterable[dict[str, Any]]) -> str:
    lines = [
        "# DataSciBench Failure / Unsupported Review",
        "",
        "| id | group | source_type | status | format | official_scoring_status | report | trace |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        if record.get("status") == "completed" and record.get("official_scoring_status") == "scored":
            continue
        lines.append(
            "| {id} | {group} | {source} | {status} | {format_status} | {scoring} | {report} | {trace} |".format(
                id=record.get("id", ""),
                group=record.get("task_group", ""),
                source=record.get("data_source_type", ""),
                status=record.get("status", ""),
                format_status="ok" if record.get("format_compliant") else "missing",
                scoring=record.get("official_scoring_status", ""),
                report=record.get("raw_report_path", ""),
                trace=record.get("trace_path", ""),
            )
        )
    return "\n".join(lines).strip() + "\n"


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# DataSciBench Pilot Summary",
        "",
        f"- benchmark: `{summary.get('benchmark')}`",
        f"- generated_at: `{summary.get('generated_at')}`",
        f"- sample_size: `{summary.get('sample_size')}`",
        f"- completed_rate: `{summary.get('completed_rate')}`",
        f"- scored_count: `{summary.get('scored_count')}`",
        f"- unsupported_count: `{summary.get('unsupported_count')}`",
        f"- run_error_count: `{summary.get('run_error_count')}`",
        f"- format_failure_count: `{summary.get('format_failure_count')}`",
        f"- avg_duration_seconds: `{summary.get('avg_duration_seconds')}`",
        "",
        "## Interpretation",
        "",
        "- This pilot validates prompt loading and Academic-Data-Agent execution on DataSciBench-style tasks.",
        "- Official TFC/ground-truth scoring is reported as unsupported unless the HuggingFace ground-truth files are present locally.",
        "- No custom substitute score is reported.",
    ]
    return "\n".join(lines).strip() + "\n"


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _run_single_task(*, runner: Callable[..., Any], task: DataSciBenchTask, config: DataSciBenchRunConfig, data_path: Path) -> Any:
    return runner(
        data_path,
        query=build_datascibench_query(task),
        output_dir=config.output_root,
        env_file=config.env_file,
        max_steps=config.max_steps,
        quality_mode=config.quality_mode,
        latency_mode=config.latency_mode,
        vision_review_mode=config.vision_review_mode,
        use_rag=False,
        use_memory=False,
        task_type="datascibench",
        task_expectations=(),
        symbolic_profile=config.symbolic_profile,
    )


def run_datascibench_sample(
    config: DataSciBenchRunConfig,
    *,
    runner: Callable[..., Any] = run_analysis,
) -> dict[str, Any]:
    all_tasks = load_datascibench_tasks(config.data_root, allow_download=config.allow_download)
    selected_tasks = select_datascibench_tasks(
        all_tasks,
        task_ids=config.task_ids,
        sample_size=config.sample_size,
        seed=config.seed,
        data_source_type=config.data_source_type,
        task_group=config.task_group,
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = config.reports_dir / timestamp
    report_dir.mkdir(parents=True, exist_ok=True)
    progress_log_path = report_dir / "progress.log"
    responses_path = report_dir / "responses.jsonl"
    summary_path = report_dir / "eval_datascibench_summary.json"
    summary_markdown_path = report_dir / "eval_datascibench_summary.md"
    failure_review_path = report_dir / "failure_review.md"
    run_config_path = report_dir / "run_config.json"
    run_config_path.write_text(
        json.dumps(
            {
                **asdict(config),
                "data_root": config.data_root.as_posix(),
                "reports_dir": config.reports_dir.as_posix(),
                "output_root": config.output_root.as_posix(),
                "env_file": config.env_file.as_posix() if config.env_file else None,
                "selected_task_count": len(selected_tasks),
                "selected_task_ids": [task.task_id for task in selected_tasks],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    records: list[dict[str, Any]] = []
    _append_progress(progress_log_path, f"run_started selected_task_count={len(selected_tasks)}")
    for index, task in enumerate(selected_tasks, start=1):
        started_at = perf_counter()
        start_message = f"[{index}/{len(selected_tasks)}] DataSciBench task {task.task_id} | source={task.data_source_type}"
        print(start_message, flush=True)
        _append_progress(progress_log_path, start_message)
        input_path = create_placeholder_dataset(task, config.data_root / "synthetic_inputs")
        record: dict[str, Any] = {
            "id": task.task_id,
            "task_group": task.task_group,
            "data_source_type": task.data_source_type,
            "status": "pending",
            "official_scoring_status": _official_scoring_status(task, config.data_root),
            "duration_seconds": 0.0,
            "raw_report_path": "",
            "trace_path": "",
            "run_dir": "",
            "attempt_count": 0,
            "prompt_path": task.prompt_path.as_posix(),
        }
        try:
            result = None
            last_exc: Exception | None = None
            for attempt in range(1, max(0, config.task_retries) + 2):
                record["attempt_count"] = attempt
                try:
                    result = _run_single_task(runner=runner, task=task, config=config, data_path=input_path)
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt <= config.task_retries:
                        _append_progress(progress_log_path, f"retry task={task.task_id} attempt={attempt} error={exc}")
                        continue
                    raise
            if result is None and last_exc is not None:
                raise last_exc
            report_markdown = str(getattr(result, "report_markdown", "") or "")
            format_compliant, extracted_result, result_source = extract_datascibench_result_block(report_markdown)
            raw_report_path = _save_raw_report(report_dir, task.task_id, report_markdown)
            record.update(
                {
                    "status": "completed",
                    "raw_report_path": raw_report_path.as_posix(),
                    "trace_path": getattr(getattr(result, "trace_path", ""), "as_posix", lambda: str(getattr(result, "trace_path", "")))(),
                    "run_dir": getattr(getattr(result, "run_dir", ""), "as_posix", lambda: str(getattr(result, "run_dir", "")))(),
                    "workflow_complete": bool(getattr(result, "workflow_complete", False)),
                    "execution_audit_passed": bool(getattr(result, "execution_audit_passed", False)),
                    "format_compliant": format_compliant,
                    "datascibench_result": extracted_result,
                    "datascibench_result_source": result_source,
                }
            )
        except Exception as exc:
            error_path = report_dir / f"{task.task_id}_error.txt"
            error_path.write_text(traceback.format_exc(), encoding="utf-8")
            record.update({"status": "failed", "error": str(exc), "error_path": error_path.as_posix()})
        finally:
            record["duration_seconds"] = round(perf_counter() - started_at, 3)
            records.append(record)
            _write_jsonl(responses_path, records)
            summary = build_summary(records=records, config=config, report_dir=report_dir)
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            summary_markdown_path.write_text(render_summary_markdown(summary), encoding="utf-8")
            failure_review_path.write_text(render_failure_review(records), encoding="utf-8")
            done_message = f"[{index}/{len(selected_tasks)}] done | status={record['status']} | scoring={record['official_scoring_status']}"
            print(done_message, flush=True)
            _append_progress(progress_log_path, done_message)
    _append_progress(progress_log_path, "run_finished")
    return {
        "report_dir": report_dir.as_posix(),
        "responses_path": responses_path.as_posix(),
        "summary_path": summary_path.as_posix(),
        "summary_markdown_path": summary_markdown_path.as_posix(),
        "failure_review_path": failure_review_path.as_posix(),
        "progress_log_path": progress_log_path.as_posix(),
        "run_config_path": run_config_path.as_posix(),
        "summary": build_summary(records=records, config=config, report_dir=report_dir),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a DataSciBench pilot through Academic-Data-Agent.")
    parser.add_argument("--data-root", default="data/external/datascibench")
    parser.add_argument("--reports-dir", default="eval/reports/datascibench")
    parser.add_argument("--output-root", default="outputs")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--task-ids", default="")
    parser.add_argument("--data-source-type", default="1")
    parser.add_argument("--task-group", default="csv_excel")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--task-retries", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--quality-mode", choices=("draft", "standard", "publication"), default="draft")
    parser.add_argument("--latency-mode", choices=("auto", "quality", "fast"), default="quality")
    parser.add_argument("--symbolic-profile", choices=("full", "prompt_only", "none"), default="full")
    parser.add_argument("--vision-review-mode", choices=("off", "auto", "on"), default="off")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = DataSciBenchRunConfig(
        data_root=_resolve_path(args.data_root).resolve(),
        reports_dir=_resolve_path(args.reports_dir).resolve(),
        output_root=_resolve_path(args.output_root).resolve(),
        env_file=_resolve_path(args.env_file).resolve() if args.env_file else None,
        sample_size=args.sample_size,
        seed=args.seed,
        task_ids=tuple(item.strip() for item in str(args.task_ids).split(",") if item.strip()),
        allow_download=not args.no_download,
        data_source_type=args.data_source_type,
        task_group=args.task_group,
        max_steps=args.max_steps,
        quality_mode=args.quality_mode,
        latency_mode=args.latency_mode,
        symbolic_profile=args.symbolic_profile,
        vision_review_mode=args.vision_review_mode,
        task_retries=max(0, args.task_retries),
    )
    result = run_datascibench_sample(config)
    print(f"DataSciBench report directory: {result['report_dir']}")
    print(f"DataSciBench summary: {result['summary_path']}")
    print(f"DataSciBench progress log: {result['progress_log_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
