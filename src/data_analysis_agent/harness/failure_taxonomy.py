"""Objective failure taxonomy for the first harness version."""

from __future__ import annotations

from ..runtime_models import AnalysisRunResult


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = str(text or "").lower()
    return any(keyword in normalized for keyword in keywords)


def classify_failure_types(result: AnalysisRunResult) -> tuple[str, ...]:
    failure_types: list[str] = []
    if result.execution_audit_status != "passed":
        failure_types.append("cleaning_contract_failure")
    if (not result.workflow_complete) and result.missing_artifacts:
        failure_types.append("artifact_contract_failure")
    if result.rag_uncited_sections_detected or result.rag_evidence_coverage_status in {"missing_citations", "invalid"}:
        failure_types.append("citation_evidence_failure")
    critique = str(result.review_critique or "")
    if _contains_any(critique, ("citation", "evidence", "uncited", "reference", "引文", "证据", "引用")):
        failure_types.append("citation_evidence_failure")
    if result.vision_review_status in {"failed"} or _contains_any(
        critique,
        ("chart", "figure", "plot", "visual", "图表", "图", "可视化"),
    ):
        failure_types.append("chart_quality_failure")
    if result.review_status in {"rejected", "max_reviews_reached"}:
        failure_types.append("review_rejection")
    if not failure_types and (not result.workflow_complete or result.review_status != "accepted"):
        failure_types.append("unknown_failure")
    return tuple(dict.fromkeys(failure_types))


def determine_primary_failure_type(result: AnalysisRunResult) -> str:
    failure_types = classify_failure_types(result)
    return failure_types[0] if failure_types else "none"
