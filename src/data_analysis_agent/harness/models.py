"""Data models for the local harness and eval workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    title: str
    data_path: str
    resolved_data_path: Path
    question: str
    task_type: str
    knowledge_paths: tuple[str, ...] = ()
    resolved_knowledge_paths: tuple[Path, ...] = ()
    quality_mode: str = "standard"
    latency_mode: str = "auto"
    use_rag: bool = True
    use_memory: bool = True
    memory_scope_key: str = "eval-default"
    expected_methods: tuple[str, ...] = ()
    key_checks: tuple[str, ...] = ()
    manual_expectations: tuple[str, ...] = ()
    common_failures: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["resolved_data_path"] = self.resolved_data_path.as_posix()
        payload["resolved_knowledge_paths"] = [path.as_posix() for path in self.resolved_knowledge_paths]
        return payload


@dataclass(frozen=True)
class EvalRunSummary:
    task_id: str
    title: str
    run_id: str
    run_dir: str
    data_path: str
    question: str
    accepted: bool
    review_status: str
    workflow_complete: bool
    execution_audit_status: str
    execution_audit_passed: bool
    report_contract_passed: bool
    report_contract_issue_count: int
    report_contract_issue_types: tuple[str, ...]
    failure_types: tuple[str, ...]
    primary_failure_type: str
    key_check_results: dict[str, bool]
    rag_enabled: bool
    memory_enabled: bool
    success_memory_match_count: int
    failure_memory_match_count: int
    rag_match_count: int
    methods_used: tuple[str, ...]
    tools_used: tuple[str, ...]
    figure_count: int
    step_count: int
    duration_seconds: float
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BaselineSnapshot:
    baseline_name: str
    created_at: str
    task_count: int
    accept_rate: float
    workflow_complete_rate: float
    execution_audit_pass_rate: float
    review_reject_rate: float
    avg_step_count: float
    avg_duration_seconds: float
    failure_type_distribution: dict[str, int]
    task_results: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegressionRules:
    max_accept_rate_drop: float = 0.05
    max_workflow_complete_rate_drop: float = 0.05
    max_execution_audit_pass_rate_drop: float = 0.01
    max_review_reject_rate_increase: float = 0.05
    max_avg_step_count_increase: float = 2.0
    max_avg_duration_ratio_increase: float = 0.3

    def to_dict(self) -> dict[str, float]:
        return asdict(self)
