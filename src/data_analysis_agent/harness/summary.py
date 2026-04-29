"""Summary builders for eval runs and run-level harness artifacts."""

from __future__ import annotations

from .failure_taxonomy import classify_failure_types, determine_primary_failure_type
from .models import EvalRunSummary, TaskSpec
from ..runtime_models import AnalysisRunResult

_CAUSAL_LANGUAGE_HINTS = ("导致", "引发", "造成", "证明", "cause", "causes", "caused by", "drives", "impact on")
_NON_CAUSAL_QUALIFIERS = ("相关", "关联", "association", "associated", "correlation", "non-causal", "does not establish")


def detect_causal_language_violation(report_markdown: str) -> bool:
    normalized = str(report_markdown or "").lower()
    if not any(token.lower() in normalized for token in _CAUSAL_LANGUAGE_HINTS):
        return False
    return not any(token.lower() in normalized for token in _NON_CAUSAL_QUALIFIERS)


def evaluate_key_checks(result: AnalysisRunResult, key_checks: tuple[str, ...]) -> dict[str, bool]:
    figure_count = len(tuple(result.telemetry.figures_generated))
    checks = {
        "must_workflow_complete": bool(result.workflow_complete),
        "must_create_cleaned_data": bool(result.cleaned_data_path.exists()),
        "must_pass_execution_audit": bool(result.execution_audit_passed),
        "must_generate_report": bool(result.report_path.exists()),
        "must_generate_trace": bool(result.trace_path.exists()),
        "must_generate_at_least_one_chart": figure_count >= 1,
    }
    return {check_name: checks.get(check_name, False) for check_name in key_checks}


def build_eval_run_summary(task: TaskSpec, result: AnalysisRunResult) -> EvalRunSummary:
    failure_types = classify_failure_types(result)
    return EvalRunSummary(
        task_id=task.task_id,
        title=task.title,
        run_id=result.run_dir.name,
        run_dir=result.run_dir.as_posix(),
        data_path=result.data_context.absolute_path.as_posix(),
        question=task.question,
        accepted=result.review_status == "accepted",
        review_status=result.review_status,
        workflow_complete=result.workflow_complete,
        execution_audit_status=result.execution_audit_status,
        execution_audit_passed=result.execution_audit_passed,
        report_contract_passed=result.report_contract_passed,
        report_contract_issue_count=len(tuple(result.report_contract_blocking_issues)),
        report_contract_issue_types=tuple(result.report_contract_issue_types),
        failure_types=failure_types,
        primary_failure_type=failure_types[0] if failure_types else "none",
        key_check_results=evaluate_key_checks(result, task.key_checks),
        rag_enabled=result.rag_enabled,
        memory_enabled=result.memory_enabled,
        success_memory_match_count=result.memory_match_count,
        failure_memory_match_count=result.failure_memory_match_count,
        rag_match_count=result.rag_match_count,
        methods_used=tuple(result.methods_used),
        tools_used=tuple(result.tools_used),
        figure_count=len(tuple(result.telemetry.figures_generated)),
        step_count=len(tuple(result.step_traces)),
        duration_seconds=round(result.total_duration_ms / 1000.0, 3),
        warnings=tuple(result.workflow_warnings),
        symbolic_profile=result.symbolic_profile,
        statistical_validity="not_reviewed",
        causal_language_violation=detect_causal_language_violation(result.report_markdown),
    )


def build_run_summary_payload(result: AnalysisRunResult) -> dict[str, object]:
    failure_types = classify_failure_types(result)
    return {
        "run_id": result.run_dir.name,
        "symbolic_profile": result.symbolic_profile,
        "data_path": result.data_context.absolute_path.as_posix(),
        "review_status": result.review_status,
        "workflow_complete": result.workflow_complete,
        "execution_audit_status": result.execution_audit_status,
        "execution_audit_passed": result.execution_audit_passed,
        "report_contract_passed": result.report_contract_passed,
        "report_contract_blocking_issues": list(result.report_contract_blocking_issues),
        "report_contract_issue_types": list(result.report_contract_issue_types),
        "missing_artifacts": list(result.missing_artifacts),
        "failure_types": list(failure_types),
        "primary_failure_type": determine_primary_failure_type(result),
        "methods_used": list(result.methods_used),
        "tools_used": list(result.tools_used),
        "figure_count": len(tuple(result.telemetry.figures_generated)),
        "step_count": len(tuple(result.step_traces)),
        "rag_match_count": result.rag_match_count,
        "success_memory_match_count": result.memory_match_count,
        "failure_memory_match_count": result.failure_memory_match_count,
        "duration_seconds": round(result.total_duration_ms / 1000.0, 3),
        "statistical_validity": "not_reviewed",
        "causal_language_violation": detect_causal_language_violation(result.report_markdown),
    }
