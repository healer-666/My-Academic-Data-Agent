"""Review and reviewer-log helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .data_context import DataContextSummary
from .reporting import EvidenceCoverage, ReportTelemetry, _iter_markdown_sections
from .rag.models import RetrievedChunk
from .runtime_models import (
    AgentStepTrace,
    ArtifactValidationResult,
    ParsedReviewerReply,
    ReviewerEvidenceFinding,
    ReviewRecord,
    StageExecutionAuditResult,
    VisualReviewRecord,
)
from .vision_review import VisualReviewResult


_REPORT_SECTION_HINTS: dict[str, tuple[str, ...]] = {
    "data_overview": ("\u6570\u636e\u6982\u89c8", "data overview", "overview"),
    "cleaning_notes": (
        "\u6570\u636e\u6e05\u6d17",
        "\u6e05\u6d17\u8bf4\u660e",
        "data cleaning",
        "cleaning notes",
        "preprocessing",
    ),
    "methods": ("\u65b9\u6cd5\u8bf4\u660e", "methods", "method"),
    "core_results": (
        "\u4e3b\u8981\u7edf\u8ba1\u7ed3\u679c",
        "\u6838\u5fc3\u7edf\u8ba1\u7ed3\u679c",
        "results",
        "statistical results",
    ),
    "figure_interpretation": (
        "\u56fe\u8868\u89e3\u91ca",
        "\u7ed3\u679c\u89e3\u91ca",
        "figure interpretation",
        "result interpretation",
    ),
    "limitations": ("\u5c40\u9650\u6027", "\u9650\u5236", "limitations", "limitation"),
    "conclusion": ("\u7ed3\u8bba", "conclusion"),
}
_LIMITATION_BODY_HINTS = (
    "\u5c40\u9650",
    "\u9650\u5236",
    "sample size",
    "small sample",
    "non-causal",
    "limitation",
    "limitations",
)
_FIGURE_WORD_HINTS = ("\u56fe", "figure", "chart", "plot")
_FIGURE_INTERPRETATION_HINTS = (
    "\u663e\u793a",
    "\u8868\u660e",
    "\u8bf4\u660e",
    "\u63d0\u793a",
    "shows",
    "indicates",
    "suggests",
    "reveals",
)
_PAIRED_HINTS = (
    "\u914d\u5bf9",
    "\u524d\u540e",
    "\u540c\u4e00\u5bf9\u8c61",
    "before-after",
    "pre-post",
    "paired",
    "repeated",
)
_MISSING_HINTS = ("\u7f3a\u5931", "missing", "impute", "dropna")
_OUTLIER_HINTS = ("\u5f02\u5e38\u503c", "\u79bb\u7fa4", "outlier", "extreme value")
_SMALL_SAMPLE_HINTS = ("\u5c0f\u6837\u672c", "sample size", "small sample", "n=")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = str(text or "").lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def _inspect_report_structure(report_markdown: str) -> dict[str, object]:
    sections = _iter_markdown_sections(report_markdown or "")
    normalized_sections = [(str(title or "").lower(), str(body or "").lower()) for title, body in sections]
    normalized_report = str(report_markdown or "").lower()
    section_presence: dict[str, bool] = {}
    for key, hints in _REPORT_SECTION_HINTS.items():
        section_presence[key] = any(any(hint.lower() in title for hint in hints) for title, _ in normalized_sections) or any(
            re.search(rf"^#+\s+.*{re.escape(hint.lower())}", normalized_report, re.MULTILINE) is not None
            for hint in hints
        )
    if not section_presence["limitations"]:
        section_presence["limitations"] = any(
            _contains_any(body, _LIMITATION_BODY_HINTS) for _, body in normalized_sections
        ) or _contains_any(normalized_report, _LIMITATION_BODY_HINTS)

    figure_reference_count = len(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", report_markdown or ""))
    figure_interpretation_hit_count = sum(
        1
        for line in (report_markdown or "").splitlines()
        if _contains_any(line, _FIGURE_WORD_HINTS) and _contains_any(line, _FIGURE_INTERPRETATION_HINTS)
    )
    return {
        "section_presence": section_presence,
        "figure_reference_count": figure_reference_count,
        "figure_interpretation_hit_count": figure_interpretation_hit_count,
        "paired_or_prepost_mentioned": _contains_any(normalized_report, _PAIRED_HINTS),
        "missing_value_handling_mentioned": _contains_any(normalized_report, _MISSING_HINTS),
        "outlier_handling_mentioned": _contains_any(normalized_report, _OUTLIER_HINTS),
        "small_sample_limitation_mentioned": _contains_any(normalized_report, _SMALL_SAMPLE_HINTS),
    }


def _format_report_structure_summary(
    report_markdown: str,
    *,
    task_type: str = "",
    task_expectations: tuple[str, ...] = (),
) -> str:
    inspection = _inspect_report_structure(report_markdown)
    section_presence = inspection["section_presence"]
    lines = [
        f"- task_type: {task_type or 'not_provided'}",
        "- task_expectations:",
    ]
    if task_expectations:
        lines.extend(f"  - {item}" for item in task_expectations)
    else:
        lines.append("  - none")
    lines.extend(
        [
            "- report_structure_presence:",
            f"  - data_overview: {section_presence['data_overview']}",
            f"  - cleaning_notes: {section_presence['cleaning_notes']}",
            f"  - methods: {section_presence['methods']}",
            f"  - core_results: {section_presence['core_results']}",
            f"  - figure_interpretation: {section_presence['figure_interpretation']}",
            f"  - limitations: {section_presence['limitations']}",
            f"  - conclusion: {section_presence['conclusion']}",
            f"- figure_reference_count: {inspection['figure_reference_count']}",
            f"- figure_interpretation_hit_count: {inspection['figure_interpretation_hit_count']}",
            f"- paired_or_prepost_mentioned: {inspection['paired_or_prepost_mentioned']}",
            f"- missing_value_handling_mentioned: {inspection['missing_value_handling_mentioned']}",
            f"- outlier_handling_mentioned: {inspection['outlier_handling_mentioned']}",
            f"- small_sample_limitation_mentioned: {inspection['small_sample_limitation_mentioned']}",
        ]
    )
    return "\n".join(lines)


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

    evidence_findings = _parse_evidence_findings(payload.get("evidence_findings"))
    return ParsedReviewerReply(
        decision=decision,
        critique=critique,
        raw_response=raw_response,
        evidence_findings=evidence_findings,
    )


def safe_parse_reviewer_reply(raw_response: str, extract_first_json_object: Any) -> ParsedReviewerReply:
    try:
        return parse_reviewer_reply(raw_response, extract_first_json_object)
    except ValueError as exc:
        critique = (
            "Reviewer response could not be parsed. Treat this as a rejection and revise the report. "
            f"Parsing issue: {exc}"
        )
        return ParsedReviewerReply(decision="Reject", critique=critique, raw_response=raw_response)


def _parse_evidence_findings(value: Any) -> tuple[ReviewerEvidenceFinding, ...]:
    if not isinstance(value, list):
        return ()
    findings: list[ReviewerEvidenceFinding] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        finding_type = str(item.get("type", "")).strip() or "other"
        message = str(item.get("message", "")).strip()
        if not message:
            continue
        findings.append(
            ReviewerEvidenceFinding(
                finding_type=finding_type,
                message=message,
                citation_label=str(item.get("citation_label", "")).strip(),
            )
        )
    return tuple(findings)


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
    evidence_register: tuple[RetrievedChunk, ...] = (),
    evidence_coverage: EvidenceCoverage | None = None,
    memory_context: str = "",
    execution_audit: StageExecutionAuditResult | None = None,
    task_type: str = "",
    task_expectations: tuple[str, ...] = (),
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
    round_figures = [figure_path for figure_path in telemetry.figures_generated if round_pattern.search(str(figure_path))]
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
    coverage = evidence_coverage or EvidenceCoverage(status="not_checked")
    evidence_lines = []
    for chunk in evidence_register:
        evidence_lines.append(
            f"- {chunk.evidence_id} | {chunk.citation_label} | locator={chunk.source_locator} | excerpt={chunk.text[:180].strip()}"
        )
    evidence_register_block = "\n".join(evidence_lines) if evidence_lines else "- none"
    cited_labels = "\n".join(f"- {item}" for item in coverage.used_citation_labels) if coverage.used_citation_labels else "- none"
    invalid_labels = (
        "\n".join(f"- {item}" for item in coverage.invalid_citation_labels)
        if coverage.invalid_citation_labels
        else "- none"
    )
    uncited_sections = (
        "\n".join(f"- {item}" for item in coverage.uncited_knowledge_sections_detected)
        if coverage.uncited_knowledge_sections_detected
        else "- none"
    )
    memory_block = memory_context.strip() or "- none"
    active_execution_audit = execution_audit or StageExecutionAuditResult(status="not_checked")
    audit_findings = (
        "\n".join(
            f"- step={finding.step_index if finding.step_index is not None else 'n/a'} | {finding.message}"
            for finding in active_execution_audit.findings
        )
        if active_execution_audit.findings
        else "- none"
    )
    report_structure_summary = _format_report_structure_summary(
        report_markdown,
        task_type=task_type,
        task_expectations=task_expectations,
    )

    return (
        f"Review round: {review_round}\n"
        f"Candidate report path: {report_path.as_posix()}\n\n"
        "Dataset metadata summary:\n"
        f"{data_context.context_text}\n"
        "Task alignment summary:\n"
        f"{report_structure_summary}\n\n"
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
        "Evidence review context:\n"
        f"- evidence_coverage_status: {coverage.status}\n"
        f"- citation_count: {coverage.citation_count}\n"
        f"- used_evidence_ids: {', '.join(coverage.used_evidence_ids) if coverage.used_evidence_ids else 'none'}\n"
        f"- cited_sources: {', '.join(coverage.cited_sources) if coverage.cited_sources else 'none'}\n"
        "Final evidence register:\n"
        f"{evidence_register_block}\n"
        "Citations used in report:\n"
        f"{cited_labels}\n"
        "Invalid citation labels:\n"
        f"{invalid_labels}\n"
        "Uncited knowledge sections detected:\n"
        f"{uncited_sections}\n\n"
        "Project memory context:\n"
        f"{memory_block}\n\n"
        "Stage execution audit:\n"
        f"- status: {active_execution_audit.status}\n"
        f"- passed: {active_execution_audit.passed}\n"
        f"- stage1_save_detected: {active_execution_audit.stage1_save_detected}\n"
        f"- stage2_cleaned_reload_detected: {active_execution_audit.stage2_cleaned_reload_detected}\n"
        f"- raw_data_reused_after_stage1: {active_execution_audit.raw_data_reused_after_stage1}\n"
        f"- evidence_step_indices: {', '.join(str(item) for item in active_execution_audit.evidence_step_indices) if active_execution_audit.evidence_step_indices else 'none'}\n"
        "Stage audit findings:\n"
        f"{audit_findings}\n\n"
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


def build_stage_audit_rejection(audit_result: StageExecutionAuditResult) -> ParsedReviewerReply:
    findings = [finding.message for finding in audit_result.findings]
    critique = (
        "\u9636\u6bb5\u6267\u884c\u5ba1\u8ba1\u672a\u901a\u8fc7\uff1a"
        f"status={audit_result.status}\uff0c"
        "\u7cfb\u7edf\u672a\u80fd\u8bc1\u660e\u8be5\u8f6e\u5206\u6790\u9075\u5b88"
        "\u201c\u5148\u4fdd\u5b58 cleaned_data.csv\uff0c\u518d\u5728\u540e\u7eed Python \u6b65\u9aa4\u4e2d\u663e\u5f0f\u91cd\u8bfb\u5e76\u5206\u6790\u201d"
        "\u7684\u4e24\u9636\u6bb5\u5951\u7ea6\u3002"
    )
    if findings:
        critique = critique + " \u5177\u4f53\u95ee\u9898\uff1a" + " | ".join(findings)
    payload = {
        "decision": "Reject",
        "critique": critique,
        "source": "stage_execution_audit",
        "stage_execution_audit_status": audit_result.status,
        "stage_execution_audit_findings": findings,
    }
    return ParsedReviewerReply(
        decision="Reject",
        critique=critique,
        raw_response=json.dumps(payload, ensure_ascii=False),
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
        "evidence_findings": [
            {
                "type": finding.finding_type,
                "message": finding.message,
                "citation_label": finding.citation_label,
            }
            for finding in reviewer_reply.evidence_findings
        ],
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
            "evidence_findings": [
                {
                    "type": finding.finding_type,
                    "message": finding.message,
                    "citation_label": finding.citation_label,
                }
                for finding in review.evidence_findings
            ],
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
