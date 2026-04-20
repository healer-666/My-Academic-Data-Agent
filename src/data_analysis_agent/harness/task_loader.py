"""Task loading and lightweight validation for eval specs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import TaskSpec

ALLOWED_KEY_CHECKS = {
    "must_workflow_complete",
    "must_create_cleaned_data",
    "must_pass_execution_audit",
    "must_generate_report",
    "must_generate_trace",
    "must_generate_at_least_one_chart",
}

REQUIRED_TASK_FIELDS = {
    "task_id",
    "title",
    "data_path",
    "question",
    "task_type",
}


def _load_yaml_like(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(raw_text)
    except Exception:
        payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError(f"Task spec must be a mapping: {path.as_posix()}")
    return payload


def load_task_spec(path: str | Path, *, project_root: str | Path | None = None) -> TaskSpec:
    spec_path = Path(path).resolve()
    root = Path(project_root).resolve() if project_root is not None else Path.cwd().resolve()
    payload = _load_yaml_like(spec_path)
    missing = sorted(field for field in REQUIRED_TASK_FIELDS if not str(payload.get(field, "")).strip())
    if missing:
        raise ValueError(f"Task spec missing required fields {missing}: {spec_path.as_posix()}")
    key_checks = tuple(str(item).strip() for item in payload.get("key_checks", []) if str(item).strip())
    invalid_checks = sorted(item for item in key_checks if item not in ALLOWED_KEY_CHECKS)
    if invalid_checks:
        raise ValueError(f"Task spec contains unsupported key checks {invalid_checks}: {spec_path.as_posix()}")
    resolved_data_path = (root / str(payload["data_path"])).resolve()
    return TaskSpec(
        task_id=str(payload["task_id"]).strip(),
        title=str(payload["title"]).strip(),
        data_path=str(payload["data_path"]).strip(),
        resolved_data_path=resolved_data_path,
        question=str(payload["question"]).strip(),
        task_type=str(payload["task_type"]).strip(),
        quality_mode=str(payload.get("quality_mode", "standard")).strip() or "standard",
        latency_mode=str(payload.get("latency_mode", "auto")).strip() or "auto",
        use_rag=bool(payload.get("use_rag", True)),
        use_memory=bool(payload.get("use_memory", True)),
        memory_scope_key=str(payload.get("memory_scope_key", "eval-default")).strip() or "eval-default",
        expected_methods=tuple(str(item).strip() for item in payload.get("expected_methods", []) if str(item).strip()),
        key_checks=key_checks,
        manual_expectations=tuple(
            str(item).strip() for item in payload.get("manual_expectations", []) if str(item).strip()
        ),
        common_failures=tuple(str(item).strip() for item in payload.get("common_failures", []) if str(item).strip()),
        notes=str(payload.get("notes", "")).strip(),
    )


def load_task_specs(task_glob: str, *, project_root: str | Path | None = None) -> tuple[TaskSpec, ...]:
    root = Path(project_root).resolve() if project_root is not None else Path.cwd().resolve()
    matched_paths = sorted(root.glob(task_glob))
    if not matched_paths:
        raise FileNotFoundError(f"No task specs matched pattern: {task_glob}")
    return tuple(load_task_spec(path, project_root=root) for path in matched_paths if path.is_file())
