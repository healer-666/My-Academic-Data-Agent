"""Baseline aggregation and persistence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import BaselineSnapshot, EvalRunSummary


def aggregate_baseline_snapshot(*, baseline_name: str, summaries: tuple[EvalRunSummary, ...]) -> BaselineSnapshot:
    task_count = len(summaries)
    accept_count = sum(1 for item in summaries if item.accepted)
    workflow_complete_count = sum(1 for item in summaries if item.workflow_complete)
    audit_pass_count = sum(1 for item in summaries if item.execution_audit_passed)
    review_reject_count = sum(1 for item in summaries if item.review_status in {"rejected", "max_reviews_reached"})
    total_steps = sum(item.step_count for item in summaries)
    total_duration = sum(item.duration_seconds for item in summaries)
    failure_distribution: dict[str, int] = {}
    for item in summaries:
        for failure_type in item.failure_types:
            failure_distribution[failure_type] = failure_distribution.get(failure_type, 0) + 1
    task_results = tuple(
        {
            "task_id": item.task_id,
            "accepted": item.accepted,
            "review_status": item.review_status,
            "workflow_complete": item.workflow_complete,
            "execution_audit_status": item.execution_audit_status,
            "primary_failure_type": item.primary_failure_type,
            "duration_seconds": item.duration_seconds,
            "step_count": item.step_count,
        }
        for item in summaries
    )
    divisor = max(task_count, 1)
    return BaselineSnapshot(
        baseline_name=baseline_name,
        created_at=datetime.now().isoformat(timespec="seconds"),
        task_count=task_count,
        accept_rate=accept_count / divisor,
        workflow_complete_rate=workflow_complete_count / divisor,
        execution_audit_pass_rate=audit_pass_count / divisor,
        review_reject_rate=review_reject_count / divisor,
        avg_step_count=total_steps / divisor,
        avg_duration_seconds=total_duration / divisor,
        failure_type_distribution=failure_distribution,
        task_results=task_results,
    )


def save_baseline_snapshot(snapshot: BaselineSnapshot, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_baseline_snapshot(path: str | Path) -> BaselineSnapshot:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return BaselineSnapshot(
        baseline_name=str(payload["baseline_name"]),
        created_at=str(payload["created_at"]),
        task_count=int(payload["task_count"]),
        accept_rate=float(payload["accept_rate"]),
        workflow_complete_rate=float(payload["workflow_complete_rate"]),
        execution_audit_pass_rate=float(payload["execution_audit_pass_rate"]),
        review_reject_rate=float(payload["review_reject_rate"]),
        avg_step_count=float(payload["avg_step_count"]),
        avg_duration_seconds=float(payload["avg_duration_seconds"]),
        failure_type_distribution={str(key): int(value) for key, value in dict(payload["failure_type_distribution"]).items()},
        task_results=tuple(dict(item) for item in payload.get("task_results", [])),
    )
