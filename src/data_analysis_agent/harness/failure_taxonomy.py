"""Failure taxonomy helpers for harness summaries."""

from __future__ import annotations

from ..runtime_models import AnalysisRunResult


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = str(text or "").lower()
    return any(keyword.lower() in normalized for keyword in keywords)


_STRUCTURE_HINTS = (
    "\u7f3a\u5c11\u6e05\u6d17\u8bf4\u660e",
    "\u6e05\u6d17\u8bf4\u660e",
    "\u7f3a\u5c11\u5c40\u9650\u6027",
    "\u5c40\u9650\u6027",
    "\u672a\u8bf4\u660e\u914d\u5bf9\u7ed3\u6784",
    "\u914d\u5bf9\u7ed3\u6784",
    "\u672a\u8bf4\u660e\u524d\u540e",
    "missing structure",
    "cleaning note",
    "limitations section",
    "paired structure",
)
_FIGURE_INTERPRETATION_HINTS = (
    "\u56fe\u8868\u5df2\u5f15\u7528\u4f46\u672a\u89e3\u91ca",
    "\u56fe\u8868\u89e3\u91ca\u4e0d\u8db3",
    "\u6709\u56fe\u65e0\u89e3\u91ca",
    "figure explanation",
    "figure is cited but not explained",
    "chart explanation",
    "plot explanation",
)
_CITATION_HINTS = (
    "citation",
    "evidence",
    "uncited",
    "reference",
    "invalid citation",
    "citation mismatch",
    "\u5f15\u6587",
    "\u8bc1\u636e",
    "\u5f15\u7528",
)


def classify_failure_types(result: AnalysisRunResult) -> tuple[str, ...]:
    failure_types: list[str] = []
    review_failed = result.review_status in {"rejected", "max_reviews_reached"}

    if result.execution_audit_status != "passed":
        failure_types.append("cleaning_contract_failure")
    if (not result.workflow_complete) and result.missing_artifacts:
        failure_types.append("artifact_contract_failure")
    if result.rag_uncited_sections_detected or result.rag_evidence_coverage_status in {"missing_citations", "invalid", "invalid_citations", "invalid_and_missing"}:
        failure_types.append("citation_evidence_failure")

    contract_issue_types = set(result.report_contract_issue_types)
    if review_failed and "report_structure_failure" in contract_issue_types:
        failure_types.append("report_structure_failure")
    if review_failed and "figure_interpretation_failure" in contract_issue_types:
        failure_types.append("figure_interpretation_failure")
    if review_failed and "citation_evidence_failure" in contract_issue_types:
        failure_types.append("citation_evidence_failure")
    if review_failed:
        failure_types.append("review_rejection")

    if not failure_types and (not result.workflow_complete or result.review_status != "accepted"):
        failure_types.append("unknown_failure")
    return tuple(dict.fromkeys(failure_types))


def determine_primary_failure_type(result: AnalysisRunResult) -> str:
    failure_types = classify_failure_types(result)
    return failure_types[0] if failure_types else "none"
