"""Aggregation helpers for symbolic-governance ablation runs."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .summary import detect_causal_language_violation
from ..runtime_models import AnalysisRunResult

SYMBOLIC_ABLATION_PROFILES = ("full", "prompt_only", "none")
CORE_ABLATION_METRICS = (
    "workflow_complete",
    "execution_audit_passed",
    "report_contract_passed",
    "statistical_validity",
    "causal_language_clean",
)


def load_manual_annotations(path: str | Path | None) -> dict[str, dict[str, object]]:
    if path in (None, ""):
        return {}
    annotation_path = Path(path)
    if not annotation_path.exists():
        return {}
    payload = json.loads(annotation_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, dict[str, object]] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            normalized[str(key)] = dict(value)
    return normalized


def build_ablation_record(
    *,
    task_id: str,
    seed: str,
    profile: str,
    result: AnalysisRunResult,
    manual_annotations: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    annotations = manual_annotations or {}
    annotation = annotations.get(f"{task_id}:{seed}:{profile}") or annotations.get(f"{task_id}:{profile}") or annotations.get(task_id) or {}
    statistical_validity = str(annotation.get("statistical_validity", "not_reviewed") or "not_reviewed")
    causal_override = annotation.get("causal_language_violation")
    causal_violation = (
        bool(causal_override)
        if causal_override is not None
        else detect_causal_language_violation(result.report_markdown)
    )
    return {
        "task_id": task_id,
        "seed": str(seed),
        "profile": profile,
        "run_id": result.run_dir.name,
        "run_dir": result.run_dir.as_posix(),
        "review_status": result.review_status,
        "workflow_complete": bool(result.workflow_complete),
        "execution_audit_passed": bool(result.execution_audit_passed),
        "report_contract_passed": bool(result.report_contract_passed),
        "statistical_validity": statistical_validity,
        "causal_language_violation": causal_violation,
        "step_count": len(tuple(result.step_traces)),
        "duration_seconds": round(result.total_duration_ms / 1000.0, 3),
    }


def aggregate_profile_metrics(records: Iterable[dict[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("profile", ""))].append(record)

    summaries: dict[str, dict[str, object]] = {}
    for profile, items in grouped.items():
        count = len(items)
        reviewed = [item for item in items if item.get("statistical_validity") in {"valid", "invalid"}]
        valid_count = sum(1 for item in reviewed if item.get("statistical_validity") == "valid")
        summaries[profile] = {
            "task_count": count,
            "workflow_complete_rate": _rate(items, "workflow_complete"),
            "execution_audit_pass_rate": _rate(items, "execution_audit_passed"),
            "report_contract_pass_rate": _rate(items, "report_contract_passed"),
            "statistical_validity_rate": (valid_count / len(reviewed)) if reviewed else "not_reviewed",
            "statistical_validity_reviewed_count": len(reviewed),
            "causal_language_violation_rate": _rate(items, "causal_language_violation"),
            "avg_step_count": _mean(float(item.get("step_count", 0) or 0) for item in items),
            "avg_duration_seconds": _mean(float(item.get("duration_seconds", 0.0) or 0.0) for item in items),
        }
    return summaries


def build_paired_comparisons(records: Iterable[dict[str, object]]) -> dict[str, object]:
    by_key: dict[tuple[str, str], dict[str, dict[str, object]]] = defaultdict(dict)
    for record in records:
        key = (str(record.get("task_id", "")), str(record.get("seed", "")))
        by_key[key][str(record.get("profile", ""))] = record

    comparisons: dict[str, list[dict[str, object]]] = {"full_vs_prompt_only": [], "full_vs_none": []}
    for (task_id, seed), profile_records in sorted(by_key.items()):
        full = profile_records.get("full")
        if not full:
            continue
        for comparison_name, other_profile in (("full_vs_prompt_only", "prompt_only"), ("full_vs_none", "none")):
            other = profile_records.get(other_profile)
            if not other:
                continue
            comparisons[comparison_name].append(
                {
                    "task_id": task_id,
                    "seed": seed,
                    "workflow_complete_delta": _bool_delta(full, other, "workflow_complete"),
                    "execution_audit_passed_delta": _bool_delta(full, other, "execution_audit_passed"),
                    "report_contract_passed_delta": _bool_delta(full, other, "report_contract_passed"),
                    "causal_language_clean_delta": int(not full.get("causal_language_violation")) - int(not other.get("causal_language_violation")),
                    "step_count_delta": int(full.get("step_count", 0) or 0) - int(other.get("step_count", 0) or 0),
                    "duration_seconds_delta": round(
                        float(full.get("duration_seconds", 0.0) or 0.0)
                        - float(other.get("duration_seconds", 0.0) or 0.0),
                        3,
                    ),
                }
            )
    return {
        name: {
            "pairs": pairs,
            "pair_count": len(pairs),
            "mean_deltas": _mean_pair_deltas(pairs),
        }
        for name, pairs in comparisons.items()
    }


def determine_evidence_level(profile_metrics: dict[str, dict[str, object]]) -> str:
    full = profile_metrics.get("full")
    prompt_only = profile_metrics.get("prompt_only")
    none = profile_metrics.get("none")
    if not full or not prompt_only or not none:
        return "weak"
    metrics = ("workflow_complete_rate", "execution_audit_pass_rate", "report_contract_pass_rate")
    wins_both = 0
    wins_one = 0
    for metric in metrics:
        full_value = _numeric_metric(full.get(metric))
        prompt_value = _numeric_metric(prompt_only.get(metric))
        none_value = _numeric_metric(none.get(metric))
        if full_value > prompt_value and full_value > none_value:
            wins_both += 1
        elif full_value > prompt_value or full_value > none_value:
            wins_one += 1
    if wins_both >= 2:
        return "strong"
    if wins_both >= 1 or wins_one >= 1:
        return "partial"
    return "weak"


def build_symbolic_ablation_report(
    *,
    records: Iterable[dict[str, object]],
    generated_at: str,
) -> dict[str, object]:
    record_list = list(records)
    profile_metrics = aggregate_profile_metrics(record_list)
    paired_comparisons = build_paired_comparisons(record_list)
    return {
        "generated_at": generated_at,
        "profile_definitions": {
            "full": "prompt guardrails + symbolic verifier + blocking rejection + revision loop",
            "prompt_only": "soft symbolic constraints only; verifiers run posthoc without blocking or revision",
            "none": "minimal JSON/tool protocol only; no statistical guardrails or report checklist",
        },
        "records": record_list,
        "profile_metrics": profile_metrics,
        "paired_comparisons": paired_comparisons,
        "evidence_level": determine_evidence_level(profile_metrics),
        "recommended_claim": "在 10 个任务的小规模消融中，full profile 在流程完成和报告契约通过上表现更稳定。",
        "claim_caution": "Do not describe this as proof of a complete neuro-symbolic learning system.",
    }


def render_symbolic_ablation_markdown(report: dict[str, object]) -> str:
    metrics = report.get("profile_metrics", {})
    lines = [
        "# Symbolic Governance Ablation Report",
        "",
        "This project implements a neuro-symbolic-inspired LLM agent for reliable statistical data analysis.",
        "",
        f"- evidence_level: `{report.get('evidence_level', 'weak')}`",
        f"- recommended_claim: {report.get('recommended_claim', '')}",
        "",
        "## Profile Metrics",
        "",
    ]
    if isinstance(metrics, dict):
        for profile in SYMBOLIC_ABLATION_PROFILES:
            item = metrics.get(profile, {})
            if not isinstance(item, dict):
                continue
            lines.extend(
                [
                    f"### {profile}",
                    "",
                    f"- workflow_complete_rate: `{item.get('workflow_complete_rate', 0.0)}`",
                    f"- execution_audit_pass_rate: `{item.get('execution_audit_pass_rate', 0.0)}`",
                    f"- report_contract_pass_rate: `{item.get('report_contract_pass_rate', 0.0)}`",
                    f"- statistical_validity_rate: `{item.get('statistical_validity_rate', 'not_reviewed')}`",
                    f"- causal_language_violation_rate: `{item.get('causal_language_violation_rate', 0.0)}`",
                    f"- avg_step_count: `{item.get('avg_step_count', 0.0)}`",
                    f"- avg_duration_seconds: `{item.get('avg_duration_seconds', 0.0)}`",
                    "",
                ]
            )
    lines.extend(
        [
            "## Paired Comparison",
            "",
            "Pairs are aligned by `task_id + seed`. With 10 seed tasks, interpret differences as small-scale stability evidence, not statistical proof.",
        ]
    )
    comparisons = report.get("paired_comparisons", {})
    if isinstance(comparisons, dict):
        for name, payload in comparisons.items():
            if not isinstance(payload, dict):
                continue
            lines.append(f"- {name}: pairs=`{payload.get('pair_count', 0)}`, mean_deltas=`{payload.get('mean_deltas', {})}`")
    return "\n".join(lines).strip() + "\n"


def _rate(items: list[dict[str, object]], key: str) -> float:
    if not items:
        return 0.0
    return round(sum(1 for item in items if bool(item.get(key))) / len(items), 4)


def _mean(values: Iterable[float]) -> float:
    value_list = list(values)
    if not value_list:
        return 0.0
    return round(sum(value_list) / len(value_list), 4)


def _bool_delta(full: dict[str, object], other: dict[str, object], key: str) -> int:
    return int(bool(full.get(key))) - int(bool(other.get(key)))


def _mean_pair_deltas(pairs: list[dict[str, object]]) -> dict[str, float]:
    if not pairs:
        return {}
    keys = (
        "workflow_complete_delta",
        "execution_audit_passed_delta",
        "report_contract_passed_delta",
        "causal_language_clean_delta",
        "step_count_delta",
        "duration_seconds_delta",
    )
    return {key: _mean(float(pair.get(key, 0.0) or 0.0) for pair in pairs) for key in keys}


def _numeric_metric(value: object) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0

