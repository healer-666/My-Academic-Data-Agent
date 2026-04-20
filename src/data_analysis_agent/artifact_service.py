"""Run-context, artifact validation, and trace persistence helpers."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .document_ingestion import IngestionResult
from .events import AgentEvent
from .reporting import ReportTelemetry
from .review_service import serialize_review_history, serialize_visual_review_history
from .runtime_models import (
    AgentStepTrace,
    AnalystRoundRecord,
    ArtifactValidationResult,
    ReviewRecord,
    RunContext,
    StageExecutionAuditResult,
    VisualReviewRecord,
    WorkflowState,
)


def create_run_directory(output_dir: str | Path) -> tuple[Path, Path, Path, Path]:
    parent_dir = Path(output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = parent_dir / f"run_{timestamp}"
    data_dir = run_dir / "data"
    figures_dir = run_dir / "figures"
    logs_dir = run_dir / "logs"
    for directory in (data_dir, figures_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return run_dir, data_dir, figures_dir, logs_dir


def build_run_context(
    *,
    source_path: Path,
    output_dir: str | Path,
    quality_mode: str,
    latency_mode: str,
    vision_review_mode: str,
    document_ingestion_mode: str,
    selected_table_id: str | None = None,
    session_id: str | None = None,
    run_dir_parts: tuple[Path, Path, Path, Path] | None = None,
) -> RunContext:
    run_dir, data_dir, figures_dir, logs_dir = run_dir_parts or create_run_directory(output_dir)
    run_id = run_dir.name
    return RunContext(
        run_id=run_id,
        session_id=session_id or run_id,
        source_path=source_path.resolve(),
        output_root=Path(output_dir).resolve(),
        run_dir=run_dir,
        data_dir=data_dir,
        figures_dir=figures_dir,
        logs_dir=logs_dir,
        cleaned_data_path=data_dir / "cleaned_data.csv",
        report_path=run_dir / "final_report.md",
        trace_path=logs_dir / "agent_trace.json",
        quality_mode=quality_mode,
        latency_mode=latency_mode,
        vision_review_mode=vision_review_mode,
        document_ingestion_mode=document_ingestion_mode,
        selected_table_id=str(selected_table_id or "").strip(),
    )


def build_run_context_text(run_context: RunContext, *, figures_dir: Path | None = None) -> str:
    return run_context.build_run_context_text(figures_dir=figures_dir)


def validate_artifacts(
    *,
    cleaned_data_path: Path,
    report_path: Path,
    trace_path: Path,
    telemetry: ReportTelemetry,
    execution_audit: StageExecutionAuditResult | None = None,
) -> ArtifactValidationResult:
    missing_artifacts: list[str] = []
    warnings: list[str] = []

    cleaned_data_exists = cleaned_data_path.exists()
    report_exists = report_path.exists()
    trace_exists = trace_path.exists()

    if not cleaned_data_exists:
        missing_artifacts.append(cleaned_data_path.as_posix())
    if not report_exists:
        missing_artifacts.append(report_path.as_posix())
    if not trace_exists:
        missing_artifacts.append(trace_path.as_posix())

    if telemetry.cleaned_data_saved and not cleaned_data_exists:
        warnings.append("Telemetry claimed cleaned_data.csv was saved, but the file does not exist.")
    if telemetry.cleaned_data_path and telemetry.cleaned_data_path != cleaned_data_path.as_posix():
        warnings.append("Telemetry cleaned_data_path does not match the canonical run artifact path.")
    if not telemetry.valid:
        warnings.append("Final report telemetry block is missing or malformed.")
    active_audit = execution_audit or StageExecutionAuditResult(status="not_checked")
    stage_contract_findings = tuple(finding.message for finding in active_audit.findings)
    stage_contract_passed = active_audit.passed if execution_audit is not None else True
    if execution_audit is not None and not active_audit.passed:
        warnings.append(f"Stage execution audit did not pass: {active_audit.status}.")
        warnings.extend(stage_contract_findings)

    workflow_complete = cleaned_data_exists and report_exists and trace_exists and telemetry.valid and stage_contract_passed
    if not workflow_complete:
        warnings.append("This run did not complete the production-grade artifact contract.")

    return ArtifactValidationResult(
        workflow_complete=workflow_complete,
        missing_artifacts=tuple(missing_artifacts),
        warnings=tuple(warnings),
        cleaned_data_exists=cleaned_data_exists,
        report_exists=report_exists,
        trace_exists=trace_exists,
        stage_contract_status=active_audit.status,
        stage_contract_findings=stage_contract_findings,
        stage_contract_passed=stage_contract_passed,
    )


def build_review_figures_dir(figures_root: Path, review_round: int) -> Path:
    review_figures_dir = figures_root / f"review_round_{review_round}"
    review_figures_dir.mkdir(parents=True, exist_ok=True)
    return review_figures_dir


def reindex_step_traces(step_traces: list[AgentStepTrace], start_index: int) -> tuple[AgentStepTrace, ...]:
    return tuple(
        AgentStepTrace(
            step_index=start_index + offset,
            raw_response=trace.raw_response,
            action=trace.action,
            decision=trace.decision,
            tool_name=trace.tool_name,
            tool_status=trace.tool_status,
            observation=trace.observation,
            observation_preview=trace.observation_preview,
            summary=trace.summary,
            parse_error=trace.parse_error,
            llm_duration_ms=trace.llm_duration_ms,
            tool_duration_ms=trace.tool_duration_ms,
        )
        for offset, trace in enumerate(step_traces)
    )


def save_agent_trace(
    *,
    trace_path: Path,
    runtime_config: Any,
    data_context: Any,
    run_context: RunContext,
    max_steps: int,
    effective_max_steps: int,
    step_traces: tuple[AgentStepTrace, ...],
    telemetry: ReportTelemetry,
    search_status: str,
    search_notes: str,
    tools_used: tuple[str, ...],
    artifact_validation: ArtifactValidationResult,
    analysis_rounds: tuple[AnalystRoundRecord, ...],
    review_history: tuple[ReviewRecord, ...],
    visual_review_history: tuple[VisualReviewRecord, ...],
    document_ingestion: IngestionResult,
    review_status: str,
    review_enabled: bool,
    search_enabled: bool,
    fast_path_enabled: bool,
    small_simple_dataset: bool,
    vision_configured: bool,
    timing_breakdown: dict[str, int],
    workflow_states: tuple[WorkflowState, ...] = (),
    event_stream: tuple[AgentEvent, ...] = (),
    rag_payload: dict[str, object] | None = None,
    memory_payload: dict[str, object] | None = None,
    failure_memory_payload: dict[str, object] | None = None,
    execution_audit: StageExecutionAuditResult | None = None,
) -> Path:
    active_rag_payload = dict(rag_payload or {})
    active_memory_payload = dict(memory_payload or {})
    active_failure_memory_payload = dict(failure_memory_payload or {})
    active_execution_audit = execution_audit or StageExecutionAuditResult(status="not_checked")
    payload = {
        "run_metadata": {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "model_id": runtime_config.model_id,
            "max_steps": max_steps,
            "effective_max_steps": effective_max_steps,
            "data_path": data_context.absolute_path.as_posix(),
            "input_kind": document_ingestion.input_kind,
            "run_dir": run_context.run_dir.as_posix(),
            "run_id": run_context.run_id,
            "session_id": run_context.session_id,
            "quality_mode": run_context.quality_mode,
            "latency_mode": run_context.latency_mode,
            "vision_review_mode": run_context.vision_review_mode,
            "document_ingestion_mode": run_context.document_ingestion_mode,
            "review_enabled": review_enabled,
            "search_enabled": search_enabled,
            "fast_path_enabled": fast_path_enabled,
            "small_simple_dataset": small_simple_dataset,
            "vision_configured": vision_configured,
            "rag_enabled": bool(active_rag_payload.get("enabled", False)),
            "rag_status": str(active_rag_payload.get("status", "disabled")),
            "knowledge_paths": list(active_rag_payload.get("knowledge_paths", [])),
            "memory_enabled": bool(active_memory_payload.get("enabled", False)),
            "memory_scope_key": str(active_memory_payload.get("scope_key", "")),
            "memory_writeback_status": str(active_memory_payload.get("writeback_status", "disabled")),
            "failure_memory_enabled": bool(active_failure_memory_payload.get("enabled", False)),
            "failure_memory_writeback_status": str(active_failure_memory_payload.get("writeback_status", "disabled")),
        },
        "workflow_states": [state.value if isinstance(state, WorkflowState) else str(state) for state in workflow_states],
        "event_stream": [event.to_dict() for event in event_stream],
        "step_traces": [asdict(trace) for trace in step_traces],
        "analysis_rounds": [
            {
                "round_index": round_record.round_index,
                "report_path": round_record.report_path.as_posix(),
                "step_traces": [asdict(trace) for trace in round_record.step_traces],
                "execution_audit": round_record.execution_audit.to_trace_dict(),
            }
            for round_record in analysis_rounds
        ],
        "review_history": serialize_review_history(review_history),
        "vision_review_history": serialize_visual_review_history(visual_review_history),
        "document_ingestion": {
            "input_kind": document_ingestion.input_kind,
            "status": document_ingestion.status,
            "summary": document_ingestion.summary,
            "normalized_data_path": document_ingestion.normalized_data_path.as_posix(),
            "duration_ms": document_ingestion.duration_ms,
            "log_path": document_ingestion.log_path.as_posix() if document_ingestion.log_path else None,
            "parsed_document_path": (
                document_ingestion.parsed_document_path.as_posix()
                if document_ingestion.parsed_document_path
                else None
            ),
            "selected_table_id": document_ingestion.selected_table_id,
            "candidate_table_count": document_ingestion.candidate_table_count,
            "selected_table_shape": list(document_ingestion.selected_table_shape)
            if document_ingestion.selected_table_shape
            else None,
            "selected_table_headers": list(document_ingestion.selected_table_headers),
            "selected_table_numeric_columns": list(document_ingestion.selected_table_numeric_columns),
            "candidate_table_summaries": list(document_ingestion.candidate_table_summaries),
            "pdf_multi_table_mode": document_ingestion.pdf_multi_table_mode,
            "warnings": list(document_ingestion.warnings),
        },
        "telemetry": {
            "methods": list(telemetry.methods),
            "domain": telemetry.domain,
            "tools_used": list(tools_used),
            "search_used": telemetry.search_used,
            "search_notes": search_notes,
            "cleaned_data_saved": telemetry.cleaned_data_saved,
            "cleaned_data_path": telemetry.cleaned_data_path,
            "figures_generated": list(telemetry.figures_generated),
            "telemetry_valid": telemetry.valid,
            "telemetry_warning": telemetry.warning,
        },
        "artifact_validation": {
            "workflow_complete": artifact_validation.workflow_complete,
            "missing_artifacts": list(artifact_validation.missing_artifacts),
            "warnings": list(artifact_validation.warnings),
            "cleaned_data_exists": artifact_validation.cleaned_data_exists,
            "report_exists": artifact_validation.report_exists,
            "trace_exists": artifact_validation.trace_exists,
            "stage_contract_status": artifact_validation.stage_contract_status,
            "stage_contract_findings": list(artifact_validation.stage_contract_findings),
            "stage_contract_passed": artifact_validation.stage_contract_passed,
        },
        "execution_audit": active_execution_audit.to_trace_dict(),
        "search_status": search_status,
        "review_status": review_status,
        "timing_breakdown": dict(timing_breakdown),
        "rag": active_rag_payload,
        "memory": active_memory_payload,
        "success_memory": active_memory_payload,
        "failure_memory": active_failure_memory_payload,
    }
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return trace_path


def save_run_summary(
    *,
    summary_path: Path,
    payload: dict[str, object],
) -> Path:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path
