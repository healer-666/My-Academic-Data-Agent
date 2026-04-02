"""Review and reviewer-log helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .data_context import DataContextSummary
from .reporting import ReportTelemetry
from .runtime_models import (
    AgentStepTrace,
    ArtifactValidationResult,
    ParsedReviewerReply,
    ReviewRecord,
    VisualReviewRecord,
)
from .vision_review import VisualReviewResult


def parse_reviewer_reply(raw_response: str, extract_first_json_object: Any) -> ParsedReviewerReply:
    json_payload = extract_first_json_object(raw_response)
    try:
        payload = json.loads(json_payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid reviewer JSON response: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Reviewer response JSON must be an object.")

    decision = str(payload.get("decision", "")).strip()
    if decision not in {"Accept", "Reject"}:
        raise ValueError("Reviewer field 'decision' must be either 'Accept' or 'Reject'.")

    critique = str(payload.get("critique", "")).strip()
    if not critique:
        raise ValueError("Reviewer field 'critique' must be a non-empty string.")

    return ParsedReviewerReply(decision=decision, critique=critique, raw_response=raw_response)


def safe_parse_reviewer_reply(raw_response: str, extract_first_json_object: Any) -> ParsedReviewerReply:
    try:
        return parse_reviewer_reply(raw_response, extract_first_json_object)
    except ValueError as exc:
        critique = (
            "Reviewer response could not be parsed. Treat this as a rejection and revise the report. "
            f"Parsing issue: {exc}"
        )
        return ParsedReviewerReply(decision="Reject", critique=critique, raw_response=raw_response)


def should_attempt_vision_review(*, quality_mode: str, review_enabled: bool, vision_review_mode: str) -> bool:
    if not review_enabled or vision_review_mode == "off":
        return False
    if vision_review_mode == "on":
        return quality_mode in {"standard", "publication"}
    return quality_mode == "publication"


def default_max_reviews_for_mode(quality_mode: str) -> int:
    return {"draft": 0, "standard": 1, "publication": 2}[quality_mode]


def build_visual_review_summary(review: VisualReviewResult) -> str:
    parts = [
        f"- status: {review.status}",
        f"- decision: {review.decision}",
        f"- summary: {review.summary}",
    ]
    if review.figures_reviewed:
        parts.append("- figures_reviewed:")
        parts.extend(f"  - {item}" for item in review.figures_reviewed)
    if review.skipped_figures:
        parts.append("- skipped_figures:")
        parts.extend(f"  - {item}" for item in review.skipped_figures)
    if review.findings:
        parts.append("- findings:")
        for finding in review.findings:
            parts.append(
                f"  - {finding.figure} | severity={finding.severity} | issue={finding.issue} | fix={finding.suggested_fix}"
            )
    return "\n".join(parts)


def build_reviewer_task(
    *,
    data_context: DataContextSummary,
    report_markdown: str,
    report_path: Path,
    step_traces: tuple[AgentStepTrace, ...],
    artifact_validation: ArtifactValidationResult,
    telemetry: ReportTelemetry,
    review_round: int,
    visual_review_summary: str = "",
) -> str:
    trace_lines = []
    for trace in step_traces:
        trace_lines.append(
            f"- Step {trace.step_index} | tool={trace.tool_name or 'finalize'} | "
            f"status={trace.tool_status} | summary={trace.summary or trace.decision or 'n/a'}"
        )
    trace_summary = "\n".join(trace_lines) if trace_lines else "- No execution trace available."
    missing = ", ".join(artifact_validation.missing_artifacts) if artifact_validation.missing_artifacts else "none"
    warnings = "; ".join(artifact_validation.warnings) if artifact_validation.warnings else "none"
    round_pattern = re.compile(rf"review_round_{review_round}(?:/|\\)")
    round_figures = [
        figure_path
        for figure_path in telemetry.figures_generated
        if round_pattern.search(str(figure_path))
    ]
    if not round_figures:
        round_figures = list(telemetry.figures_generated)
    figure_evidence_lines = []
    for figure_path in round_figures:
        figure_file = Path(figure_path)
        figure_evidence_lines.append(
            f"- {figure_file.name} | path={figure_file.as_posix()} | exists={figure_file.exists()}"
        )
    figures_block = "\n".join(figure_evidence_lines) if figure_evidence_lines else "- none"
    figures_dir = report_path.parent / "figures" / f"review_round_{review_round}"

    return (
        f"Review round: {review_round}\n"
        f"Candidate report path: {report_path.as_posix()}\n\n"
        "Dataset metadata summary:\n"
        f"{data_context.context_text}\n"
        "Execution trace summary:\n"
        f"{trace_summary}\n\n"
        "Generated artifacts evidence:\n"
        f"- telemetry_figures_generated_count: {len(telemetry.figures_generated)}\n"
        f"- review_round_figures_generated_count: {len(round_figures)}\n"
        f"- review_round_figures_dir: {figures_dir.as_posix()}\n"
        f"- review_round_figures_dir_exists: {figures_dir.exists()}\n"
        f"- candidate_report_path: {report_path.as_posix()}\n"
        f"- artifact_workflow_complete: {artifact_validation.workflow_complete}\n"
        f"- artifact_missing_artifacts: {missing}\n"
        f"- artifact_warnings: {warnings}\n"
        "Generated figure list:\n"
        f"{figures_block}\n\n"
        + (
            "Visual figure audit summary:\n"
            f"{visual_review_summary}\n\n"
            if visual_review_summary
            else ""
        )
        + (
            "Artifact validation summary:\n"
            f"- workflow_complete: {artifact_validation.workflow_complete}\n"
            f"- missing_artifacts: {missing}\n"
            f"- warnings: {warnings}\n\n"
            "Candidate final_report.md content:\n"
            f"{report_markdown}"
        )
    )


def save_review_log(
    *,
    review_log_path: Path,
    review_round: int,
    reviewer_reply: ParsedReviewerReply,
    candidate_report_path: Path,
) -> Path:
    payload = {
        "round_index": review_round,
        "decision": reviewer_reply.decision,
        "critique": reviewer_reply.critique,
        "raw_response": reviewer_reply.raw_response,
        "candidate_report_path": candidate_report_path.as_posix(),
    }
    review_log_path.parent.mkdir(parents=True, exist_ok=True)
    review_log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return review_log_path


def save_visual_review_log(
    *,
    review_log_path: Path,
    review_round: int,
    reviewer_reply: VisualReviewResult,
) -> Path:
    payload = {
        "round_index": review_round,
        "status": reviewer_reply.status,
        "decision": reviewer_reply.decision,
        "summary": reviewer_reply.summary,
        "figures_reviewed": list(reviewer_reply.figures_reviewed),
        "skipped_figures": list(reviewer_reply.skipped_figures),
        "duration_ms": reviewer_reply.duration_ms,
        "warning": reviewer_reply.warning,
        "raw_response": reviewer_reply.raw_response,
        "image_metadata": list(reviewer_reply.image_metadata),
        "findings": [
            {
                "figure": finding.figure,
                "severity": finding.severity,
                "issue": finding.issue,
                "suggested_fix": finding.suggested_fix,
            }
            for finding in reviewer_reply.findings
        ],
    }
    review_log_path.parent.mkdir(parents=True, exist_ok=True)
    review_log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return review_log_path


def serialize_review_history(review_history: tuple[ReviewRecord, ...]) -> list[dict[str, Any]]:
    return [
        {
            "round_index": review.round_index,
            "decision": review.decision,
            "critique": review.critique,
            "raw_response": review.raw_response,
            "review_log_path": review.review_log_path.as_posix(),
            "candidate_report_path": review.candidate_report_path.as_posix(),
        }
        for review in review_history
    ]


def serialize_visual_review_history(visual_review_history: tuple[VisualReviewRecord, ...]) -> list[dict[str, Any]]:
    return [
        {
            "round_index": review.round_index,
            "status": review.status,
            "decision": review.decision,
            "summary": review.summary,
            "figures_reviewed": list(review.figures_reviewed),
            "skipped_figures": list(review.skipped_figures),
            "duration_ms": review.duration_ms,
            "raw_response": review.raw_response,
            "warning": review.warning,
            "log_path": review.log_path.as_posix(),
        }
        for review in visual_review_history
    ]
