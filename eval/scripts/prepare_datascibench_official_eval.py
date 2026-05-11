from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import shutil
import subprocess
import sys
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_ID = "academic-data-agent"
DEFAULT_RUN_ID = "0"
ARTIFACT_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".xlsx",
    ".xls",
    ".json",
    ".jsonl",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".html",
    ".parquet",
    ".pkl",
}


@dataclass(frozen=True)
class OfficialEvalConfig:
    summary_path: Path
    official_root: Path
    reports_dir: Path
    hf_root: Path | None = None
    model_id: str = DEFAULT_MODEL_ID
    run_id: str = DEFAULT_RUN_ID
    task_ids: tuple[str, ...] = ()
    run_official_eval: bool = False
    python_executable: str = sys.executable
    timeout_seconds: int = 600


def _resolve_path(path: str | Path, *, root: Path = PROJECT_ROOT) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_records(summary_path: Path, task_ids: Iterable[str] = ()) -> list[dict[str, Any]]:
    summary = _load_json(summary_path)
    requested = {task_id for task_id in task_ids if task_id}
    records = [dict(item) for item in summary.get("results", [])]
    if requested:
        records = [record for record in records if str(record.get("id")) in requested]
    return records


def _is_bcb_task(task_id: str) -> bool:
    return str(task_id).startswith("bcb")


def _safe_model_name(model_id: str) -> str:
    return model_id.split("/")[-1]


def _model_run_name(model_id: str, run_id: str) -> str:
    return f"{_safe_model_name(model_id)}_{run_id}"


def _copy_file(source: Path, target: Path) -> None:
    if not source.exists() or not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_tree_files(source_dir: Path, target_dir: Path) -> int:
    copied = 0
    if not source_dir.exists():
        return copied
    for source in source_dir.rglob("*"):
        if source.is_file():
            relative = source.relative_to(source_dir)
            _copy_file(source, target_dir / relative)
            copied += 1
    return copied


def _extract_path_candidates(text: str) -> set[str]:
    candidates: set[str] = set()
    for match in re.findall(r"(?<![\w.-])([\w./\\:-]+\.(?:csv|tsv|xlsx|xls|json|jsonl|txt|md|png|jpg|jpeg|pdf|html|parquet|pkl))", text, re.IGNORECASE):
        cleaned = match.strip("`'\"),.;")
        if cleaned:
            candidates.add(cleaned)
    return candidates


def _metric_text(official_root: Path, task_id: str) -> str:
    metric_path = official_root / "metric" / task_id / "metric.yaml"
    return metric_path.read_text(encoding="utf-8") if metric_path.exists() else ""


def _artifact_search_roots(record: dict[str, Any]) -> list[Path]:
    roots: list[Path] = []
    for key in ("run_dir", "trace_path", "raw_report_path"):
        value = record.get(key)
        if not value:
            continue
        path = Path(str(value))
        if path.is_file():
            path = path.parent
        if path.exists() and path not in roots:
            roots.append(path)
    for extra in (PROJECT_ROOT, PROJECT_ROOT / "outputs"):
        if extra.exists() and extra not in roots:
            roots.append(extra)
    return roots


def _find_artifact(record: dict[str, Any], candidate: str) -> Path | None:
    candidate_path = Path(candidate)
    if candidate_path.is_absolute() and candidate_path.exists() and candidate_path.is_file():
        return candidate_path
    basename = candidate_path.name
    for root in _artifact_search_roots(record):
        direct = root / candidate
        if direct.exists() and direct.is_file():
            return direct
        direct_name = root / basename
        if direct_name.exists() and direct_name.is_file():
            return direct_name
        try:
            matches = list(root.rglob(basename))
        except OSError:
            matches = []
        for match in matches:
            if match.is_file():
                return match
    return None


def _copy_referenced_artifacts(record: dict[str, Any], official_root: Path, target_dir: Path) -> list[str]:
    task_id = str(record.get("id"))
    text_parts = [_metric_text(official_root, task_id)]
    raw_report_path = Path(str(record.get("raw_report_path", "")))
    if raw_report_path.exists():
        text_parts.append(raw_report_path.read_text(encoding="utf-8", errors="ignore"))
    copied: list[str] = []
    for candidate in sorted(_extract_path_candidates("\n".join(text_parts))):
        source = _find_artifact(record, candidate)
        if source is None or source.suffix.lower() not in ARTIFACT_EXTENSIONS:
            continue
        target = target_dir / Path(candidate).name
        _copy_file(source, target)
        copied.append(target.as_posix())
    return copied


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _extract_task_func_code_from_text(text: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    lines = text.splitlines()
    import_blocks: list[str] = []
    function_block = ""
    task_func: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            start = getattr(node, "lineno", 1) - 1
            end = getattr(node, "end_lineno", node.lineno)
            import_blocks.append("\n".join(lines[start:end]))
        elif isinstance(node, ast.FunctionDef) and node.name == "task_func":
            task_func = node
            start = getattr(node, "lineno", 1) - 1
            end = getattr(node, "end_lineno", None)
            if end is None:
                def_indent = len(lines[start]) - len(lines[start].lstrip())
                end = start + 1
                while end < len(lines):
                    line = lines[end]
                    stripped = line.strip()
                    indent = len(line) - len(line.lstrip())
                    if stripped and indent <= def_indent:
                        break
                    end += 1
            function_block = "\n".join(lines[start:end])
            break
    if task_func is None:
        return ""
    return "\n".join([*import_blocks, function_block]).strip()


def extract_task_func_code(trace_path: Path, raw_report_path: Path | None = None) -> str:
    texts: list[str] = []
    if str(trace_path) not in {"", "."} and trace_path.exists() and trace_path.is_file():
        try:
            payload = _load_json(trace_path)
            texts.extend(text for text in _iter_strings(payload) if "def task_func" in text)
        except Exception:
            texts.append(trace_path.read_text(encoding="utf-8", errors="ignore"))
    if raw_report_path and raw_report_path.exists() and raw_report_path.is_file():
        texts.append(raw_report_path.read_text(encoding="utf-8", errors="ignore"))
    for text in texts:
        code = _extract_task_func_code_from_text(text)
        if code:
            return code
    for text in texts:
        match = re.search(r"```(?:python)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            code = _extract_task_func_code_from_text(match.group(1))
            if code:
                return code
    return ""


def stage_bcb_output(record: dict[str, Any], config: OfficialEvalConfig) -> dict[str, Any]:
    task_id = str(record.get("id"))
    task_dir = config.official_root / "data" / task_id
    trace_path = Path(str(record.get("trace_path", "")))
    raw_report_path = Path(str(record.get("raw_report_path", "")))
    code = extract_task_func_code(trace_path, raw_report_path)
    output_path = task_dir / f"{config.model_id}_outputs.jsonl"
    status = "prepared" if code else "unsupported_missing_task_func_code"
    if code:
        output_record = {
            "output_dir": str(record.get("run_dir", "")),
            "time_cost": float(record.get("duration_seconds", 0.0) or 0.0),
            "error_list": [],
            "cost": [0, 0, 0, 0],
            "plan": [
                {
                    "task_id": "1",
                    "dependent_task_ids": [],
                    "instruction": "Academic-Data-Agent extracted task_func implementation",
                    "task_type": "coding",
                    "code": code,
                    "result": "",
                    "is_success": True,
                    "is_finished": True,
                }
            ],
        }
        _write_jsonl(output_path, [output_record])
    return {
        "id": task_id,
        "task_group": record.get("task_group"),
        "official_eval_kind": "bcb_tmc",
        "official_input_path": output_path.as_posix(),
        "official_prepare_status": status,
        "extracted_code_chars": len(code),
    }


def stage_regular_output(record: dict[str, Any], config: OfficialEvalConfig) -> dict[str, Any]:
    task_id = str(record.get("id"))
    task_dir = config.official_root / "data" / task_id
    run_dir = task_dir / _model_run_name(config.model_id, config.run_id)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    source_run_dir = Path(str(record.get("run_dir", "")))
    copied_count = _copy_tree_files(source_run_dir, run_dir)
    raw_report_path = Path(str(record.get("raw_report_path", "")))
    if raw_report_path.exists():
        _copy_file(raw_report_path, run_dir / "final_report.md")
    trace_path = Path(str(record.get("trace_path", "")))
    if trace_path.exists():
        _copy_file(trace_path, run_dir / "agent_trace.json")
    referenced = _copy_referenced_artifacts(record, config.official_root, run_dir)
    (run_dir / "logs.txt").write_text(
        f"Academic-Data-Agent completed task {task_id}; source run: {record.get('run_dir', '')}\n",
        encoding="utf-8",
    )
    gt_dir = task_dir / "gt"
    status = "prepared" if gt_dir.exists() else "unsupported_missing_gt"
    return {
        "id": task_id,
        "task_group": record.get("task_group"),
        "official_eval_kind": "tfc",
        "official_input_path": run_dir.as_posix(),
        "official_prepare_status": status,
        "copied_file_count": copied_count,
        "copied_referenced_artifacts": referenced,
        "gt_dir": gt_dir.as_posix(),
    }


def _find_gt_source(hf_root: Path, task_id: str) -> Path | None:
    candidates = [
        hf_root / "extracted_ground_truth" / "gt_data" / task_id / "gt",
        hf_root / "gt_data" / task_id / "gt",
        hf_root / "data" / task_id / "gt",
        hf_root / task_id / "gt",
        hf_root / "gt" / task_id,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for candidate in hf_root.rglob("gt"):
        if candidate.is_dir() and candidate.parent.name == task_id:
            return candidate
    return None


def _find_task_data_source(hf_root: Path, task_id: str) -> Path | None:
    candidates = [
        hf_root / "DataSciBench-data" / task_id,
        hf_root / "data" / task_id,
        hf_root / task_id,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def sync_task_data(config: OfficialEvalConfig, task_ids: Iterable[str]) -> dict[str, list[str]]:
    if config.hf_root is None or not config.hf_root.exists():
        return {}
    synced: dict[str, list[str]] = {}
    for task_id in task_ids:
        if _is_bcb_task(task_id):
            continue
        source = _find_task_data_source(config.hf_root, task_id)
        if source is None:
            continue
        target = config.official_root / "data" / task_id
        target.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for path in source.rglob("*"):
            if not path.is_file() or path.name.startswith("._") or "__MACOSX" in path.parts:
                continue
            relative = path.relative_to(source)
            destination = target / relative
            _copy_file(path, destination)
            copied.append(destination.as_posix())
        synced[task_id] = copied
    return synced


def sync_ground_truth(config: OfficialEvalConfig, task_ids: Iterable[str]) -> dict[str, str]:
    if config.hf_root is None or not config.hf_root.exists():
        return {}
    synced: dict[str, str] = {}
    for task_id in task_ids:
        if _is_bcb_task(task_id):
            continue
        source = _find_gt_source(config.hf_root, task_id)
        if source is None:
            continue
        target = config.official_root / "data" / task_id / "gt"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        synced[task_id] = target.as_posix()
    return synced


def _run_command(command: list[str], *, cwd: Path, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=str(exc.stdout or ""),
            stderr=f"Timed out after {timeout_seconds} seconds\n{exc.stderr or ''}",
        )


def _parse_bcb_result(config: OfficialEvalConfig, task_id: str) -> dict[str, Any]:
    path = config.official_root / "data" / task_id / f"{config.model_id}_tmc_results.jsonl"
    if not path.exists():
        return {"official_score_status": "score_file_missing", "official_result_path": path.as_posix()}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cr_values = [float(row.get("cr", 0.0) or 0.0) for row in rows if "cr" in row]
    return {
        "official_score_status": "scored",
        "official_result_path": path.as_posix(),
        "official_cr": round(sum(cr_values) / len(cr_values), 4) if cr_values else 0.0,
        "official_row_count": len(rows),
    }


def _parse_regular_result(config: OfficialEvalConfig, task_id: str, report_dir: Path) -> dict[str, Any]:
    source = config.official_root / "evaluation_results" / f"{_safe_model_name(config.model_id)}_results.csv"
    target = report_dir / "official_results" / f"{task_id}_results.csv"
    if not source.exists():
        return {"official_score_status": "score_file_missing", "official_result_path": source.as_posix()}
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    with source.open("r", encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("data_name") == task_id]
    cr_values = [float(row.get("result_cr", 0.0) or 0.0) for row in rows if row.get("result_type") == "Completion Rate"]
    return {
        "official_score_status": "scored",
        "official_result_path": target.as_posix(),
        "official_cr": round(sum(cr_values) / len(cr_values), 4) if cr_values else 0.0,
        "official_row_count": len(rows),
    }


def run_official_evaluator(config: OfficialEvalConfig, prepared: dict[str, Any], report_dir: Path) -> dict[str, Any]:
    task_id = str(prepared["id"])
    log_dir = report_dir / "official_eval_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    if prepared["official_prepare_status"] != "prepared":
        return {"official_score_status": prepared["official_prepare_status"]}
    if prepared["official_eval_kind"] == "bcb_tmc":
        command = [
            config.python_executable,
            "-m",
            "experiments.evaluate_tmc",
            "--task_id",
            task_id,
            "--model_id",
            config.model_id,
        ]
        result = _run_command(command, cwd=config.official_root, timeout_seconds=config.timeout_seconds)
        prefix = "evaluate_tmc"
        parsed = _parse_bcb_result(config, task_id) if result.returncode == 0 else {"official_score_status": "evaluator_failed"}
    else:
        command = [
            config.python_executable,
            "-m",
            "experiments.evaluate",
            "--task_id",
            task_id,
            "--model_id",
            config.model_id,
        ]
        result = _run_command(command, cwd=config.official_root, timeout_seconds=config.timeout_seconds)
        prefix = "evaluate"
        parsed = _parse_regular_result(config, task_id, report_dir) if result.returncode == 0 else {"official_score_status": "evaluator_failed"}
    stdout_path = log_dir / f"{task_id}_{prefix}_stdout.txt"
    stderr_path = log_dir / f"{task_id}_{prefix}_stderr.txt"
    stdout_path.write_text(result.stdout or "", encoding="utf-8", errors="ignore")
    stderr_path.write_text(result.stderr or "", encoding="utf-8", errors="ignore")
    return {
        **parsed,
        "official_evaluator_returncode": result.returncode,
        "official_evaluator_stdout": stdout_path.as_posix(),
        "official_evaluator_stderr": stderr_path.as_posix(),
    }


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# DataSciBench Official Evaluation Preparation",
        "",
        f"- generated_at: `{summary['generated_at']}`",
        f"- source_summary: `{summary['source_summary']}`",
        f"- model_id: `{summary['model_id']}`",
        f"- prepared_count: `{summary['prepared_count']}`",
        f"- scored_count: `{summary['scored_count']}`",
        f"- unsupported_count: `{summary['unsupported_count']}`",
        f"- evaluator_failed_count: `{summary['evaluator_failed_count']}`",
        "",
        "| id | kind | prepare | score | CR | input | result |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for record in summary["results"]:
        lines.append(
            "| {id} | {kind} | {prepare} | {score} | {cr} | {input} | {result} |".format(
                id=record.get("id", ""),
                kind=record.get("official_eval_kind", ""),
                prepare=record.get("official_prepare_status", ""),
                score=record.get("official_score_status", ""),
                cr=record.get("official_cr", ""),
                input=record.get("official_input_path", ""),
                result=record.get("official_result_path", ""),
            )
        )
    return "\n".join(lines).strip() + "\n"


def prepare_and_optionally_score(config: OfficialEvalConfig) -> dict[str, Any]:
    records = _load_records(config.summary_path, config.task_ids)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = config.reports_dir / timestamp
    report_dir.mkdir(parents=True, exist_ok=True)
    task_ids = [str(record.get("id")) for record in records]
    synced_task_data = sync_task_data(config, task_ids)
    synced_gt = sync_ground_truth(config, task_ids)
    prepared_records: list[dict[str, Any]] = []
    for record in records:
        task_id = str(record.get("id"))
        prepared = stage_bcb_output(record, config) if _is_bcb_task(task_id) else stage_regular_output(record, config)
        if task_id in synced_gt and prepared.get("official_prepare_status") == "unsupported_missing_gt":
            prepared["official_prepare_status"] = "prepared"
        if config.run_official_eval:
            prepared.update(run_official_evaluator(config, prepared, report_dir))
        else:
            prepared["official_score_status"] = "not_run"
        prepared_records.append(prepared)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_summary": config.summary_path.as_posix(),
        "official_root": config.official_root.as_posix(),
        "hf_root": config.hf_root.as_posix() if config.hf_root else None,
        "model_id": config.model_id,
        "run_id": config.run_id,
        "run_official_eval": config.run_official_eval,
        "synced_ground_truth": synced_gt,
        "synced_task_data": synced_task_data,
        "prepared_count": sum(1 for item in prepared_records if item.get("official_prepare_status") == "prepared"),
        "scored_count": sum(1 for item in prepared_records if item.get("official_score_status") == "scored"),
        "unsupported_count": sum(1 for item in prepared_records if str(item.get("official_prepare_status", "")).startswith("unsupported")),
        "evaluator_failed_count": sum(1 for item in prepared_records if item.get("official_score_status") == "evaluator_failed"),
        "results": prepared_records,
        "report_dir": report_dir.as_posix(),
    }
    summary_path = report_dir / "official_eval_summary.json"
    markdown_path = report_dir / "official_eval_summary.md"
    _write_json(summary_path, summary)
    markdown_path.write_text(render_summary_markdown(summary), encoding="utf-8")
    return {**summary, "summary_path": summary_path.as_posix(), "summary_markdown_path": markdown_path.as_posix()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare Academic-Data-Agent outputs for DataSciBench official evaluators.")
    parser.add_argument("--summary", required=True, help="DataSciBench runner eval_datascibench_summary.json path.")
    parser.add_argument("--official-root", default="data/external/datascibench_official")
    parser.add_argument("--hf-root", default="data/external/datascibench_hf")
    parser.add_argument("--reports-dir", default="eval/reports/datascibench_official")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--task-ids", default="")
    parser.add_argument("--run-official-eval", action="store_true")
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    hf_root = _resolve_path(args.hf_root).resolve() if args.hf_root else None
    config = OfficialEvalConfig(
        summary_path=_resolve_path(args.summary).resolve(),
        official_root=_resolve_path(args.official_root).resolve(),
        reports_dir=_resolve_path(args.reports_dir).resolve(),
        hf_root=hf_root,
        model_id=args.model_id,
        run_id=args.run_id,
        task_ids=tuple(item.strip() for item in str(args.task_ids).split(",") if item.strip()),
        run_official_eval=args.run_official_eval,
        python_executable=args.python_executable,
        timeout_seconds=max(30, args.timeout_seconds),
    )
    result = prepare_and_optionally_score(config)
    print(f"Official eval report directory: {result['report_dir']}")
    print(f"Official eval summary: {result['summary_path']}")
    print(f"Prepared: {result['prepared_count']} | Scored: {result['scored_count']} | Unsupported: {result['unsupported_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
