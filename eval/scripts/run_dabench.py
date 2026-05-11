from __future__ import annotations

import argparse
import contextlib
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


REMOTE_DATASET_BASE = "https://huggingface.co/datasets/infiagent/DABench/resolve/main"
QUESTIONS_NAME = "da-dev-questions.jsonl"
LABELS_NAME = "da-dev-labels.jsonl"
TABLES_DIR_NAME = "da-dev-tables"
DEFAULT_SAMPLE_SIZE = 30
DEFAULT_SEED = 20260510
DABENCH_MODE_MAX_STEPS = 16
DABENCH_MODE_LEVEL_MAX_STEPS = {
    "easy": 12,
    "medium": 16,
    "hard": 20,
}


@dataclass(frozen=True)
class DABenchTask:
    task_id: str
    question: str
    constraints: str
    answer_format: str
    file_name: str
    level: str
    table_path: Path
    common_answers: tuple[tuple[str, Any], ...]
    raw_question: dict[str, Any]
    raw_label: dict[str, Any]

    @property
    def expected_metric_names(self) -> tuple[str, ...]:
        return tuple(metric for metric, _ in self.common_answers)


@dataclass(frozen=True)
class DABenchRunConfig:
    data_root: Path
    reports_dir: Path
    output_root: Path
    env_file: Path | None = None
    sample_size: int = DEFAULT_SAMPLE_SIZE
    seed: int = DEFAULT_SEED
    task_ids: tuple[str, ...] = ()
    allow_download: bool = True
    max_steps: int = 6
    quality_mode: str = "standard"
    latency_mode: str = "auto"
    symbolic_profile: str = "full"
    vision_review_mode: str = "off"
    dabench_mode: bool = False
    task_retries: int = 0


@dataclass(frozen=True)
class ExtractedAnswer:
    answer_text: str
    metric_values: dict[str, str]
    format_compliant: bool
    missing_metrics: tuple[str, ...]
    source: str


def _resolve_path(path: str | Path, *, root: Path = PROJECT_ROOT) -> Path:
    value = Path(path)
    return value if value.is_absolute() else (root / value)


def _jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"JSONL record must be an object at {path.as_posix()}:{line_number}")
        records.append(payload)
    return records


def _record_id(record: dict[str, Any]) -> str:
    for key in ("id", "question_id", "qid", "task_id"):
        if key in record and str(record[key]).strip():
            return str(record[key]).strip()
    raise ValueError(f"DABench record is missing an id field: {record}")


def _task_sort_key(task_or_id: DABenchTask | str) -> tuple[int, str]:
    value = task_or_id.task_id if isinstance(task_or_id, DABenchTask) else str(task_or_id)
    try:
        return (0, f"{int(value):010d}")
    except Exception:
        return (1, value)


def _extract_text(record: dict[str, Any], keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            return "\n".join(str(item) for item in value if str(item).strip()).strip()
        text = str(value).strip()
        if text:
            return text
    return default


def _extract_file_name(record: dict[str, Any]) -> str:
    for key in ("file_name", "filename", "table_file", "table_path", "csv_file", "data_file"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip().replace("\\", "/")
    raise ValueError(f"DABench question is missing a table file name: {record}")


def _normalize_common_answers(label: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    raw_answers = (
        label.get("common_answers")
        or label.get("answers")
        or label.get("answer")
        or label.get("labels")
        or label.get("targets")
    )
    if raw_answers is None:
        raise ValueError(f"DABench label is missing common answers: {label}")
    normalized: list[tuple[str, Any]] = []
    if isinstance(raw_answers, dict):
        normalized.extend((str(key).strip(), value) for key, value in raw_answers.items() if str(key).strip())
    elif isinstance(raw_answers, list):
        for item in raw_answers:
            if isinstance(item, dict):
                metric = item.get("metric") or item.get("name") or item.get("answer_name") or item.get("key")
                value = item.get("value") if "value" in item else item.get("answer")
                if metric is not None:
                    normalized.append((str(metric).strip(), value))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                normalized.append((str(item[0]).strip(), item[1]))
    elif isinstance(raw_answers, str):
        normalized.extend(parse_answer_tags(raw_answers).items())
    if not normalized:
        raise ValueError(f"DABench label has no parseable common answers: {label}")
    return tuple((metric, value) for metric, value in normalized if metric)


def _asset_candidates(data_root: Path, relative_path: str) -> tuple[Path, ...]:
    relative = Path(relative_path)
    candidates = (data_root / "data" / relative, data_root / relative)
    return tuple(dict.fromkeys(candidates))


def _first_existing(candidates: Iterable[Path]) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    return None


def _remote_candidates(relative_path: str) -> tuple[str, ...]:
    quoted = quote(relative_path.replace("\\", "/"), safe="/")
    return (
        f"{REMOTE_DATASET_BASE}/data/{quoted}",
        f"{REMOTE_DATASET_BASE}/{quoted}",
    )


def _download_url(url: str, target: Path, *, timeout_seconds: int = 180, attempts: int = 3) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_target = target.with_name(f"{target.name}.tmp")
    request = Request(url, headers={"User-Agent": "Academic-Data-Agent-DABench/1.0"})
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


def _ensure_asset(data_root: Path, relative_path: str, *, allow_download: bool) -> Path:
    existing = _first_existing(_asset_candidates(data_root, relative_path))
    if existing is not None:
        return existing
    if not allow_download:
        raise FileNotFoundError(f"Missing DABench asset and downloads are disabled: {relative_path}")
    target = data_root / "data" / relative_path
    errors: list[str] = []
    for url in _remote_candidates(relative_path):
        try:
            _download_url(url, target)
            return target
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError(
        "Unable to download official DABench asset. Tried:\n- " + "\n- ".join(errors)
    )


def ensure_dabench_metadata(data_root: Path, *, allow_download: bool = True) -> tuple[Path, Path]:
    questions_path = _ensure_asset(data_root, QUESTIONS_NAME, allow_download=allow_download)
    labels_path = _ensure_asset(data_root, LABELS_NAME, allow_download=allow_download)
    return questions_path, labels_path


def ensure_dabench_tables(data_root: Path, tasks: Iterable[DABenchTask], *, allow_download: bool = True) -> tuple[DABenchTask, ...]:
    resolved: list[DABenchTask] = []
    for task in tasks:
        table_relative = f"{TABLES_DIR_NAME}/{task.file_name}"
        table_path = _ensure_asset(data_root, table_relative, allow_download=allow_download)
        resolved.append(
            DABenchTask(
                task_id=task.task_id,
                question=task.question,
                constraints=task.constraints,
                answer_format=task.answer_format,
                file_name=task.file_name,
                level=task.level,
                table_path=table_path,
                common_answers=task.common_answers,
                raw_question=task.raw_question,
                raw_label=task.raw_label,
            )
        )
    return tuple(resolved)


def load_dabench_tasks(data_root: Path, *, allow_download: bool = True) -> tuple[DABenchTask, ...]:
    questions_path, labels_path = ensure_dabench_metadata(data_root, allow_download=allow_download)
    questions = {_record_id(item): item for item in _jsonl_records(questions_path)}
    labels = {_record_id(item): item for item in _jsonl_records(labels_path)}
    missing_labels = sorted(set(questions) - set(labels), key=_task_sort_key)
    if missing_labels:
        raise ValueError(f"DABench labels are missing for question ids: {', '.join(missing_labels[:10])}")

    tasks: list[DABenchTask] = []
    for task_id in sorted(questions, key=_task_sort_key):
        question = questions[task_id]
        label = labels[task_id]
        file_name = _extract_file_name(question)
        table_path = _first_existing(_asset_candidates(data_root, f"{TABLES_DIR_NAME}/{file_name}")) or (
            data_root / "data" / TABLES_DIR_NAME / file_name
        )
        tasks.append(
            DABenchTask(
                task_id=task_id,
                question=_extract_text(question, ("question", "query", "instruction", "problem")),
                constraints=_extract_text(question, ("constraints", "constraint", "requirements"), default=""),
                answer_format=_extract_text(question, ("format", "answer_format", "output_format"), default=""),
                file_name=file_name,
                level=_extract_text(question, ("level", "difficulty", "type", "category"), default="unknown"),
                table_path=table_path,
                common_answers=_normalize_common_answers(label),
                raw_question=question,
                raw_label=label,
            )
        )
    return tuple(tasks)


def sample_dabench_tasks(tasks: Iterable[DABenchTask], *, sample_size: int, seed: int) -> tuple[DABenchTask, ...]:
    task_list = sorted(tuple(tasks), key=_task_sort_key)
    if sample_size <= 0 or sample_size >= len(task_list):
        return tuple(task_list)
    groups: dict[str, list[DABenchTask]] = {}
    for task in task_list:
        groups.setdefault(task.level or "unknown", []).append(task)
    if len(groups) <= 1:
        rng = random.Random(seed)
        shuffled = list(task_list)
        rng.shuffle(shuffled)
        return tuple(sorted(shuffled[:sample_size], key=_task_sort_key))

    total = len(task_list)
    quotas: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    for group_name, group_tasks in groups.items():
        exact_quota = sample_size * (len(group_tasks) / total)
        quota = min(len(group_tasks), int(exact_quota))
        quotas[group_name] = quota
        remainders.append((exact_quota - quota, group_name))
    remaining = sample_size - sum(quotas.values())
    for _, group_name in sorted(remainders, key=lambda item: (-item[0], item[1])):
        if remaining <= 0:
            break
        if quotas[group_name] < len(groups[group_name]):
            quotas[group_name] += 1
            remaining -= 1

    selected: list[DABenchTask] = []
    for group_name, group_tasks in sorted(groups.items()):
        rng = random.Random(f"{seed}:{group_name}")
        group_sample = list(group_tasks)
        rng.shuffle(group_sample)
        selected.extend(group_sample[: quotas[group_name]])
    if len(selected) < sample_size:
        selected_ids = {task.task_id for task in selected}
        leftovers = [task for task in task_list if task.task_id not in selected_ids]
        selected.extend(leftovers[: sample_size - len(selected)])
    return tuple(sorted(selected[:sample_size], key=_task_sort_key))


def select_dabench_tasks(
    tasks: Iterable[DABenchTask],
    *,
    task_ids: Iterable[str] = (),
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
) -> tuple[DABenchTask, ...]:
    task_list = tuple(tasks)
    explicit_ids = tuple(str(item).strip() for item in task_ids if str(item).strip())
    if not explicit_ids:
        return sample_dabench_tasks(task_list, sample_size=sample_size, seed=seed)
    by_id = {task.task_id: task for task in task_list}
    missing = [task_id for task_id in explicit_ids if task_id not in by_id]
    if missing:
        raise ValueError(f"Requested DABench task ids do not exist: {', '.join(missing)}")
    return tuple(sorted((by_id[task_id] for task_id in explicit_ids), key=_task_sort_key))


def build_dabench_query(task: DABenchTask, *, dabench_mode: bool = False) -> str:
    parts = [
        "Solve this InfiAgent-DABench closed-form data analysis task using the provided table as the only dataset.",
        f"Question:\n{task.question}",
    ]
    if task.constraints:
        parts.append(f"Constraints:\n{task.constraints}")
    if task.answer_format:
        parts.append(f"Official answer format:\n{task.answer_format}")
    final_requirement = [
        "Final answer requirement:",
        "- Include a final block delimited by <dabench_answer> and </dabench_answer>.",
        "- Inside that block, output only DABench answer tags in the form @answer_name[answer].",
        "- Preserve the answer names exactly as requested by the benchmark.",
        "- Do not include explanations or Markdown inside the DABench answer block.",
    ]
    if dabench_mode:
        final_requirement.extend(
            [
                "- This benchmark is scored only from the DABench answer tags; keep the report concise.",
                "- If a full narrative report would conflict with the benchmark format, prioritize the DABench answer block.",
                "- The final report must end with the DABench answer block so the evaluator can extract it reliably.",
            ]
        )
    parts.append("\n".join(final_requirement))
    return "\n\n".join(parts)


ANSWER_TAG_RE = re.compile(r"@([A-Za-z0-9_.:/-]+)\[([^\]]*)\]")
ANSWER_BLOCK_RE = re.compile(r"<dabench_answer>\s*(.*?)\s*</dabench_answer>", re.IGNORECASE | re.DOTALL)


def parse_answer_tags(text: str) -> dict[str, str]:
    answers: dict[str, str] = {}
    for metric, raw_value in ANSWER_TAG_RE.findall(str(text or "")):
        answers[metric.strip()] = raw_value.strip()
    return answers


def extract_dabench_answer(report_markdown: str, expected_metrics: Iterable[str]) -> ExtractedAnswer:
    expected = tuple(metric for metric in expected_metrics if str(metric).strip())
    block_match = ANSWER_BLOCK_RE.search(str(report_markdown or ""))
    source = "block" if block_match else "global"
    candidate_text = block_match.group(1).strip() if block_match else str(report_markdown or "")
    metric_values = parse_answer_tags(candidate_text)
    if not metric_values and block_match:
        metric_values = parse_answer_tags(str(report_markdown or ""))
        source = "global_fallback"
    missing = tuple(metric for metric in expected if metric not in metric_values)
    answer_text = "\n".join(f"@{metric}[{value}]" for metric, value in metric_values.items())
    return ExtractedAnswer(
        answer_text=answer_text,
        metric_values=metric_values,
        format_compliant=bool(metric_values) and not missing,
        missing_metrics=missing,
        source=source,
    )


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _normalize_string(value: Any) -> str:
    text = str(value).strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    return text.lower()


def evaluate_dabench_prediction(answer_text: str, common_answers: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    predictions = parse_answer_tags(answer_text)
    per_metric: dict[str, bool] = {}
    expected_payload: dict[str, Any] = {}
    predicted_payload: dict[str, Any] = {}
    for metric, expected_value in common_answers:
        expected_payload[metric] = expected_value
        predicted_value = predictions.get(metric)
        predicted_payload[metric] = predicted_value
        if predicted_value is None:
            per_metric[metric] = False
            continue
        expected_float = _to_float(expected_value)
        predicted_float = _to_float(predicted_value)
        if expected_float is not None and predicted_float is not None:
            per_metric[metric] = abs(expected_float - predicted_float) <= 1e-6
        else:
            per_metric[metric] = _normalize_string(expected_value) == _normalize_string(predicted_value)
    exact_match = bool(per_metric) and all(per_metric.values())
    return {
        "exact_match": exact_match,
        "per_metric": per_metric,
        "expected": expected_payload,
        "predicted": predicted_payload,
    }


def _failure_type(
    *,
    status: str,
    workflow_complete: bool,
    execution_audit_passed: bool,
    format_compliant: bool,
    exact_match: bool,
    dabench_mode: bool = False,
) -> str:
    if status != "completed":
        return "run_error"
    if dabench_mode and exact_match and format_compliant:
        return "none"
    if not workflow_complete:
        return "workflow_incomplete"
    if not execution_audit_passed:
        return "execution_audit_failure"
    if not format_compliant:
        return "format_failure"
    if not exact_match:
        return "answer_mismatch"
    return "none"


def build_summary(*, records: list[dict[str, Any]], config: DABenchRunConfig, report_dir: Path) -> dict[str, Any]:
    completed = [record for record in records if record.get("status") == "completed"]
    exact_count = sum(1 for record in completed if record.get("exact_match"))
    format_count = sum(1 for record in completed if record.get("format_compliant"))
    workflow_count = sum(1 for record in completed if record.get("workflow_complete"))
    audit_count = sum(1 for record in completed if record.get("execution_audit_passed"))
    benchmark_pass_count = sum(
        1 for record in completed if record.get("exact_match") and record.get("format_compliant")
    )
    strict_pass_count = sum(
        1
        for record in completed
        if record.get("exact_match")
        and record.get("format_compliant")
        and record.get("workflow_complete")
        and record.get("execution_audit_passed")
    )
    durations = [float(record.get("duration_seconds", 0.0) or 0.0) for record in records]
    failure_distribution: dict[str, int] = {}
    for record in records:
        failure = str(record.get("failure_type", "unknown"))
        failure_distribution[failure] = failure_distribution.get(failure, 0) + 1
    denominator = len(records) or 1
    return {
        "benchmark": "InfiAgent-DABench",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sample_size": len(records),
        "requested_sample_size": config.sample_size,
        "seed": config.seed,
        "task_ids": [record.get("id") for record in records],
        "exact_match_count": exact_count,
        "exact_match_rate": round(exact_count / denominator, 4),
        "benchmark_pass_count": benchmark_pass_count,
        "benchmark_pass_rate": round(benchmark_pass_count / denominator, 4),
        "strict_project_pass_count": strict_pass_count,
        "strict_project_pass_rate": round(strict_pass_count / denominator, 4),
        "format_compliance_rate": round(format_count / denominator, 4),
        "workflow_complete_rate": round(workflow_count / denominator, 4),
        "execution_audit_pass_rate": round(audit_count / denominator, 4),
        "avg_duration_seconds": round(sum(durations) / denominator, 3),
        "failure_type_distribution": failure_distribution,
        "evaluator": {
            "mode": "official-compatible-exact-match",
            "source": "https://github.com/InfiAgent/InfiAgent/blob/main/examples/DA-Agent/eval_closed_form.py",
        },
        "config": {
            "quality_mode": config.quality_mode,
            "latency_mode": config.latency_mode,
            "symbolic_profile": config.symbolic_profile,
            "vision_review_mode": config.vision_review_mode,
            "dabench_mode": config.dabench_mode,
            "task_retries": config.task_retries,
            "max_steps": config.max_steps,
            "use_rag": False,
            "use_memory": False,
        },
        "report_dir": report_dir.as_posix(),
        "results": records,
    }


def render_failure_review(records: Iterable[dict[str, Any]]) -> str:
    lines = [
        "# DABench Failure Review",
        "",
        "| id | level | failure_type | expected | predicted | raw_report | trace |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    failures = [record for record in records if record.get("failure_type") != "none"]
    if not failures:
        lines.extend(["", "No failures in this run."])
        return "\n".join(lines).strip() + "\n"
    for record in failures:
        expected = json.dumps(record.get("expected", {}), ensure_ascii=False)
        predicted = json.dumps(record.get("predicted", {}), ensure_ascii=False)
        lines.append(
            "| {id} | {level} | {failure} | `{expected}` | `{predicted}` | {report} | {trace} |".format(
                id=record.get("id", ""),
                level=record.get("level", ""),
                failure=record.get("failure_type", ""),
                expected=expected.replace("|", "\\|"),
                predicted=predicted.replace("|", "\\|"),
                report=record.get("raw_report_path", ""),
                trace=record.get("trace_path", ""),
            )
        )
    return "\n".join(lines).strip() + "\n"


def render_summary_markdown(summary: dict[str, Any]) -> str:
    config = summary.get("config", {})
    failure_distribution = summary.get("failure_type_distribution", {})
    lines = [
        "# DABench Evaluation Summary",
        "",
        f"- benchmark: `{summary.get('benchmark', 'InfiAgent-DABench')}`",
        f"- generated_at: `{summary.get('generated_at', '')}`",
        f"- sample_size: `{summary.get('sample_size', 0)}`",
        f"- seed: `{summary.get('seed', '')}`",
        f"- dabench_mode: `{config.get('dabench_mode', False)}`",
        f"- quality_mode: `{config.get('quality_mode', '')}`",
        f"- latency_mode: `{config.get('latency_mode', '')}`",
        "",
        "## Metrics",
        "",
        f"- exact_match_rate: `{summary.get('exact_match_rate', 0.0)}` ({summary.get('exact_match_count', 0)}/{summary.get('sample_size', 0)})",
        f"- benchmark_pass_rate: `{summary.get('benchmark_pass_rate', 0.0)}` ({summary.get('benchmark_pass_count', 0)}/{summary.get('sample_size', 0)})",
        f"- strict_project_pass_rate: `{summary.get('strict_project_pass_rate', 0.0)}` ({summary.get('strict_project_pass_count', 0)}/{summary.get('sample_size', 0)})",
        f"- format_compliance_rate: `{summary.get('format_compliance_rate', 0.0)}`",
        f"- workflow_complete_rate: `{summary.get('workflow_complete_rate', 0.0)}`",
        f"- execution_audit_pass_rate: `{summary.get('execution_audit_pass_rate', 0.0)}`",
        f"- avg_duration_seconds: `{summary.get('avg_duration_seconds', 0.0)}`",
        "",
        "## Failure Distribution",
        "",
    ]
    if isinstance(failure_distribution, dict) and failure_distribution:
        lines.extend(f"- {key}: `{value}`" for key, value in sorted(failure_distribution.items()))
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `benchmark_pass_rate` follows the relaxed DABench-mode scoring target: exact-match answer tags are primary.",
            "- `strict_project_pass_rate` keeps the original Academic-Data-Agent workflow/audit contract visible for diagnosis.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _save_raw_report(report_dir: Path, task_id: str, report_markdown: str) -> Path:
    raw_dir = report_dir / "raw_reports"
    raw_dir.mkdir(parents=True, exist_ok=True)
    report_path = raw_dir / f"{task_id}_final_report.md"
    report_path.write_text(report_markdown, encoding="utf-8")
    return report_path


def _max_steps_for_task(task: DABenchTask, config: DABenchRunConfig) -> int:
    if not config.dabench_mode:
        return config.max_steps
    return DABENCH_MODE_LEVEL_MAX_STEPS.get(task.level.lower(), config.max_steps)


def _append_progress(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def _run_single_task(
    *,
    runner: Callable[..., Any],
    task: DABenchTask,
    config: DABenchRunConfig,
) -> Any:
    max_steps = _max_steps_for_task(task, config)
    return runner(
        task.table_path,
        query=build_dabench_query(task, dabench_mode=config.dabench_mode),
        output_dir=config.output_root,
        env_file=config.env_file,
        max_steps=max_steps,
        quality_mode=config.quality_mode,
        latency_mode=config.latency_mode,
        vision_review_mode=config.vision_review_mode,
        use_rag=False,
        use_memory=False,
        task_type="dabench",
        task_expectations=(),
        symbolic_profile=config.symbolic_profile,
    )


def run_dabench_sample(
    config: DABenchRunConfig,
    *,
    runner: Callable[..., Any] = run_analysis,
) -> dict[str, Any]:
    all_tasks = load_dabench_tasks(config.data_root, allow_download=config.allow_download)
    selected_tasks = select_dabench_tasks(
        all_tasks,
        task_ids=config.task_ids,
        sample_size=config.sample_size,
        seed=config.seed,
    )
    selected_tasks = ensure_dabench_tables(config.data_root, selected_tasks, allow_download=config.allow_download)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = config.reports_dir / timestamp
    report_dir.mkdir(parents=True, exist_ok=True)
    responses_path = report_dir / "responses.jsonl"
    summary_path = report_dir / "eval_dabench_summary.json"
    summary_markdown_path = report_dir / "eval_dabench_summary.md"
    failure_review_path = report_dir / "failure_review.md"
    progress_log_path = report_dir / "progress.log"
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
                "dabench_mode_level_max_steps": dict(DABENCH_MODE_LEVEL_MAX_STEPS),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _append_progress(progress_log_path, f"run_started selected_task_count={len(selected_tasks)}")

    records: list[dict[str, Any]] = []
    for index, task in enumerate(selected_tasks, start=1):
        started_at = perf_counter()
        task_max_steps = _max_steps_for_task(task, config)
        start_message = f"[{index}/{len(selected_tasks)}] DABench task {task.task_id} | level={task.level} | max_steps={task_max_steps}"
        print(start_message, flush=True)
        _append_progress(progress_log_path, start_message)
        record: dict[str, Any] = {
            "id": task.task_id,
            "level": task.level,
            "file_name": task.file_name,
            "question": task.question,
            "response": "",
            "answer_source": "",
            "format_compliant": False,
            "missing_metrics": list(task.expected_metric_names),
            "exact_match": False,
            "workflow_complete": False,
            "execution_audit_passed": False,
            "review_status": "",
            "duration_seconds": 0.0,
            "raw_report_path": "",
            "trace_path": "",
            "run_dir": "",
            "expected": dict(task.common_answers),
            "predicted": {},
            "per_metric": {},
            "status": "pending",
            "failure_type": "unknown",
            "attempt_count": 0,
            "max_steps": task_max_steps,
        }
        try:
            result = None
            last_exc: Exception | None = None
            for attempt in range(1, max(0, config.task_retries) + 2):
                record["attempt_count"] = attempt
                try:
                    result = _run_single_task(runner=runner, task=task, config=config)
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt <= config.task_retries:
                        print(
                            f"[{index}/{len(selected_tasks)}] retrying task {task.task_id} after error: {exc}",
                            flush=True,
                        )
                        _append_progress(progress_log_path, f"retry task={task.task_id} attempt={attempt} error={exc}")
                        continue
                    raise
            if result is None and last_exc is not None:
                raise last_exc
            report_markdown = str(getattr(result, "report_markdown", "") or "")
            raw_report_path = _save_raw_report(report_dir, task.task_id, report_markdown)
            extraction = extract_dabench_answer(report_markdown, task.expected_metric_names)
            evaluation = evaluate_dabench_prediction(extraction.answer_text, task.common_answers)
            workflow_complete = bool(getattr(result, "workflow_complete", False))
            execution_audit_passed = bool(getattr(result, "execution_audit_passed", False))
            exact_match = bool(evaluation["exact_match"])
            record.update(
                {
                    "response": extraction.answer_text,
                    "answer_source": extraction.source,
                    "format_compliant": extraction.format_compliant,
                    "missing_metrics": list(extraction.missing_metrics),
                    "exact_match": exact_match,
                    "workflow_complete": workflow_complete,
                    "execution_audit_passed": execution_audit_passed,
                    "review_status": str(getattr(result, "review_status", "") or ""),
                    "raw_report_path": raw_report_path.as_posix(),
                    "trace_path": getattr(getattr(result, "trace_path", ""), "as_posix", lambda: str(getattr(result, "trace_path", "")))(),
                    "run_dir": getattr(getattr(result, "run_dir", ""), "as_posix", lambda: str(getattr(result, "run_dir", "")))(),
                    "predicted": evaluation["predicted"],
                    "per_metric": evaluation["per_metric"],
                    "status": "completed",
                }
            )
            record["failure_type"] = _failure_type(
                status="completed",
                workflow_complete=workflow_complete,
                execution_audit_passed=execution_audit_passed,
                format_compliant=extraction.format_compliant,
                exact_match=exact_match,
                dabench_mode=config.dabench_mode,
            )
        except Exception as exc:
            error_path = report_dir / f"{task.task_id}_error.txt"
            error_path.write_text(traceback.format_exc(), encoding="utf-8")
            record.update(
                {
                    "status": "failed",
                    "failure_type": "run_error",
                    "error": str(exc),
                    "error_path": error_path.as_posix(),
                }
            )
        finally:
            record["duration_seconds"] = round(perf_counter() - started_at, 3)
            records.append(record)
            _write_jsonl(responses_path, records)
            summary = build_summary(records=records, config=config, report_dir=report_dir)
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            summary_markdown_path.write_text(render_summary_markdown(summary), encoding="utf-8")
            failure_review_path.write_text(render_failure_review(records), encoding="utf-8")
            done_message = (
                f"[{index}/{len(selected_tasks)}] done | status={record['status']} | "
                f"exact_match={record['exact_match']} | failure={record['failure_type']}"
            )
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
    parser = argparse.ArgumentParser(description="Run an InfiAgent-DABench sample through Academic-Data-Agent.")
    parser.add_argument("--data-root", default="data/external/dabench", help="Local DABench mirror root.")
    parser.add_argument("--reports-dir", default="eval/reports/dabench", help="Directory for DABench eval reports.")
    parser.add_argument("--output-root", default="outputs", help="Run artifact root passed to run_analysis.")
    parser.add_argument("--env-file", default=None, help="Optional .env file path.")
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE, help="Number of tasks to sample.")
    parser.add_argument("--full-validation", action="store_true", help="Run all available DABench validation/dev tasks.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Fixed sampling seed.")
    parser.add_argument("--task-ids", default="", help="Comma-separated task ids; overrides sampling when set.")
    parser.add_argument("--no-download", action="store_true", help="Require DABench files to already exist locally.")
    parser.add_argument("--dabench-mode", action="store_true", help="Use benchmark-oriented settings and scoring.")
    parser.add_argument("--task-retries", type=int, default=None, help="Per-task retry count for transient run errors.")
    parser.add_argument("--max-steps", type=int, default=None, help="Maximum controller steps per task.")
    parser.add_argument("--quality-mode", choices=("draft", "standard", "publication"), default=None)
    parser.add_argument("--latency-mode", choices=("auto", "quality", "fast"), default=None)
    parser.add_argument("--symbolic-profile", choices=("full", "prompt_only", "none"), default="full")
    parser.add_argument("--vision-review-mode", choices=("off", "auto", "on"), default="off")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    sample_size = 0 if args.full_validation else args.sample_size
    max_steps = args.max_steps if args.max_steps is not None else (DABENCH_MODE_MAX_STEPS if args.dabench_mode else 6)
    quality_mode = args.quality_mode or ("draft" if args.dabench_mode else "standard")
    latency_mode = args.latency_mode or ("quality" if args.dabench_mode else "auto")
    task_retries = args.task_retries if args.task_retries is not None else (1 if args.dabench_mode else 0)
    config = DABenchRunConfig(
        data_root=_resolve_path(args.data_root).resolve(),
        reports_dir=_resolve_path(args.reports_dir).resolve(),
        output_root=_resolve_path(args.output_root).resolve(),
        env_file=_resolve_path(args.env_file).resolve() if args.env_file else None,
        sample_size=sample_size,
        seed=args.seed,
        task_ids=tuple(item.strip() for item in str(args.task_ids).split(",") if item.strip()),
        allow_download=not args.no_download,
        max_steps=max_steps,
        quality_mode=quality_mode,
        latency_mode=latency_mode,
        symbolic_profile=args.symbolic_profile,
        vision_review_mode=args.vision_review_mode,
        dabench_mode=args.dabench_mode,
        task_retries=max(0, task_retries),
    )
    result = run_dabench_sample(config)
    print(f"DABench report directory: {result['report_dir']}")
    print(f"DABench summary: {result['summary_path']}")
    print(f"DABench summary markdown: {result['summary_markdown_path']}")
    print(f"DABench progress log: {result['progress_log_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
