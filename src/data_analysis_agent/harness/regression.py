"""Regression comparison helpers for harness baselines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BaselineSnapshot, RegressionRules


def load_regression_rules(path: str | Path) -> RegressionRules:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return RegressionRules(
        max_accept_rate_drop=float(payload.get("max_accept_rate_drop", 0.05)),
        max_workflow_complete_rate_drop=float(payload.get("max_workflow_complete_rate_drop", 0.05)),
        max_execution_audit_pass_rate_drop=float(payload.get("max_execution_audit_pass_rate_drop", 0.01)),
        max_review_reject_rate_increase=float(payload.get("max_review_reject_rate_increase", 0.05)),
        max_avg_step_count_increase=float(payload.get("max_avg_step_count_increase", 2.0)),
        max_avg_duration_ratio_increase=float(payload.get("max_avg_duration_ratio_increase", 0.3)),
    )


def compare_baselines(
    *,
    current: BaselineSnapshot,
    baseline: BaselineSnapshot,
    rules: RegressionRules,
) -> dict[str, Any]:
    metrics = {
        "accept_rate": current.accept_rate - baseline.accept_rate,
        "workflow_complete_rate": current.workflow_complete_rate - baseline.workflow_complete_rate,
        "execution_audit_pass_rate": current.execution_audit_pass_rate - baseline.execution_audit_pass_rate,
        "review_reject_rate": current.review_reject_rate - baseline.review_reject_rate,
        "avg_step_count": current.avg_step_count - baseline.avg_step_count,
        "avg_duration_seconds": current.avg_duration_seconds - baseline.avg_duration_seconds,
    }
    duration_ratio_increase = 0.0
    if baseline.avg_duration_seconds > 0:
        duration_ratio_increase = (
            (current.avg_duration_seconds - baseline.avg_duration_seconds) / baseline.avg_duration_seconds
        )
    violations: list[str] = []
    if metrics["accept_rate"] < -rules.max_accept_rate_drop:
        violations.append("accept_rate")
    if metrics["workflow_complete_rate"] < -rules.max_workflow_complete_rate_drop:
        violations.append("workflow_complete_rate")
    if metrics["execution_audit_pass_rate"] < -rules.max_execution_audit_pass_rate_drop:
        violations.append("execution_audit_pass_rate")
    if metrics["review_reject_rate"] > rules.max_review_reject_rate_increase:
        violations.append("review_reject_rate")
    if metrics["avg_step_count"] > rules.max_avg_step_count_increase:
        violations.append("avg_step_count")
    if duration_ratio_increase > rules.max_avg_duration_ratio_increase:
        violations.append("avg_duration_seconds")
    return {
        "current_baseline": current.baseline_name,
        "baseline": baseline.baseline_name,
        "metrics": metrics,
        "duration_ratio_increase": duration_ratio_increase,
        "violations": violations,
        "passed": not violations,
    }


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    metrics = comparison.get("metrics", {})
    violations = comparison.get("violations", [])
    lines = [
        "# Harness Baseline Comparison",
        "",
        f"- Current: `{comparison.get('current_baseline', 'unknown')}`",
        f"- Baseline: `{comparison.get('baseline', 'unknown')}`",
        f"- Passed: `{comparison.get('passed', False)}`",
        "",
        "## Metric Deltas",
        "",
        f"- accept_rate: `{metrics.get('accept_rate', 0.0):+.4f}`",
        f"- workflow_complete_rate: `{metrics.get('workflow_complete_rate', 0.0):+.4f}`",
        f"- execution_audit_pass_rate: `{metrics.get('execution_audit_pass_rate', 0.0):+.4f}`",
        f"- review_reject_rate: `{metrics.get('review_reject_rate', 0.0):+.4f}`",
        f"- avg_step_count: `{metrics.get('avg_step_count', 0.0):+.4f}`",
        f"- avg_duration_seconds: `{metrics.get('avg_duration_seconds', 0.0):+.4f}`",
        f"- duration_ratio_increase: `{comparison.get('duration_ratio_increase', 0.0):+.4f}`",
        "",
        "## Violations",
        "",
    ]
    if violations:
        lines.extend(f"- `{item}`" for item in violations)
    else:
        lines.append("- none")
    return "\n".join(lines)
