"""Distill accepted and failed runs into layered memory records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any

from ..reporting import _iter_markdown_sections
from ..runtime_models import AnalysisRunResult, ReviewRecord
from .models import FailureMemoryRecord, MemoryRecord


@dataclass(frozen=True)
class ExtractionResult:
    records: tuple[MemoryRecord, ...]
    llm_distilled: bool = False
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class FailureExtractionResult:
    records: tuple[FailureMemoryRecord, ...]
    warnings: tuple[str, ...] = ()


def extract_memory_records(
    *,
    result: AnalysisRunResult,
    review_history: tuple[ReviewRecord, ...],
    memory_scope_key: str,
    llm: Any = None,
) -> ExtractionResult:
    warnings: list[str] = []
    created_at = datetime.now().isoformat(timespec="seconds")
    source_names = tuple(result.rag_cited_sources or result.rag_sources_used or ())
    source_count = len(source_names)
    record_specs = _build_rule_based_record_specs(
        result=result,
        review_history=review_history,
        source_names=source_names,
    )
    llm_distilled = False
    if llm is not None and record_specs:
        try:
            overrides = _distill_record_texts_with_llm(
                llm=llm,
                result=result,
                review_history=review_history,
                record_specs=record_specs,
            )
            if overrides:
                llm_distilled = True
                updated_specs = []
                for memory_type, text in record_specs:
                    override = str(overrides.get(memory_type, "") or "").strip()
                    updated_specs.append((memory_type, override or text))
                record_specs = tuple(updated_specs)
        except Exception as exc:
            warnings.append(f"Memory distillation fell back to rule-based extraction: {exc}")

    records = tuple(
        MemoryRecord(
            memory_id=f"memory-{result.run_dir.name}-{memory_type}",
            memory_scope_key=memory_scope_key,
            memory_type=memory_type,
            run_id=result.run_dir.name,
            source_report_path=result.report_path.as_posix(),
            detected_domain=result.detected_domain or "unknown",
            quality_mode=result.quality_mode,
            created_at=created_at,
            source_count=source_count,
            review_status=result.review_status,
            text=text,
            source_names=source_names,
        )
        for memory_type, text in record_specs
        if text.strip()
    )
    return ExtractionResult(records=records, llm_distilled=llm_distilled, warnings=tuple(warnings))


def extract_success_memory_records(
    *,
    result: AnalysisRunResult,
    review_history: tuple[ReviewRecord, ...],
    memory_scope_key: str,
    llm: Any = None,
) -> ExtractionResult:
    return extract_memory_records(
        result=result,
        review_history=review_history,
        memory_scope_key=memory_scope_key,
        llm=llm,
    )


def extract_failure_memory_records(
    *,
    result: AnalysisRunResult,
    review_history: tuple[ReviewRecord, ...],
    memory_scope_key: str,
) -> FailureExtractionResult:
    warnings: list[str] = []
    created_at = datetime.now().isoformat(timespec="seconds")
    source_names = tuple(result.rag_cited_sources or result.rag_sources_used or ())
    record_specs = _build_failure_record_specs(result=result, review_history=review_history)
    records = tuple(
        FailureMemoryRecord(
            memory_id=f"failure-{result.run_dir.name}-{failure_type}",
            memory_scope_key=memory_scope_key,
            failure_type=failure_type,
            run_id=result.run_dir.name,
            source_report_path=result.report_path.as_posix(),
            source_trace_path=result.trace_path.as_posix(),
            detected_domain=result.detected_domain or "unknown",
            quality_mode=result.quality_mode,
            created_at=created_at,
            review_status=result.review_status,
            workflow_complete=result.workflow_complete,
            execution_audit_status=result.execution_audit_status,
            trigger_stage=trigger_stage,
            text=text,
            avoidance_rule=avoidance_rule,
            source_names=source_names,
        )
        for failure_type, trigger_stage, text, avoidance_rule in record_specs
        if text.strip()
    )
    return FailureExtractionResult(records=records, warnings=tuple(warnings))


def _build_rule_based_record_specs(
    *,
    result: AnalysisRunResult,
    review_history: tuple[ReviewRecord, ...],
    source_names: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    records: list[tuple[str, str]] = []
    analysis_summary = _build_analysis_summary(result)
    if analysis_summary:
        records.append(("analysis_summary", analysis_summary))
    user_preference = _build_user_preference(result)
    if user_preference:
        records.append(("user_preference", user_preference))
    review_constraint = _build_review_constraint(result, review_history)
    if review_constraint:
        records.append(("review_constraint", review_constraint))
    rag_usage_note = _build_rag_usage_note(result, source_names)
    if rag_usage_note:
        records.append(("rag_usage_note", rag_usage_note))
    return tuple(records)


def _build_failure_record_specs(
    *,
    result: AnalysisRunResult,
    review_history: tuple[ReviewRecord, ...],
) -> tuple[tuple[str, str, str, str], ...]:
    specs: list[tuple[str, str, str, str]] = []
    critique_lines = []
    for review in review_history:
        critique_lines.extend(_extract_actionable_review_lines(review.critique))
        for finding in review.evidence_findings:
            message = _normalize_inline_text(finding.message)
            if message:
                critique_lines.append(message)
    critique_lines = list(dict.fromkeys(item for item in critique_lines if item))

    audit_findings = tuple(item for item in result.execution_audit_findings if _normalize_inline_text(item))
    if result.execution_audit_status != "passed":
        rule = (
            audit_findings[0]
            if audit_findings
            else "Do not proceed to formal analysis unless cleaned_data.csv is explicitly saved and reloaded in a later Python step."
        )
        specs.append(
            (
                "failure_constraint",
                "execution_audit",
                f"Avoid repeating the failed execution pattern. {rule}",
                "Before finishing, verify that Stage 1 saved cleaned_data.csv and Stage 2 explicitly reloaded it in a later Python step.",
            )
        )
        specs.append(
            (
                "failure_pattern",
                "execution_audit",
                f"This run failed stage execution audit with status {result.execution_audit_status}. Findings: {' | '.join(audit_findings) if audit_findings else 'No explicit findings were captured.'}",
                "Treat stage-contract violations as blocking errors and restart the analysis loop instead of forcing a finish.",
            )
        )

    if result.review_status in {"rejected", "max_reviews_reached"}:
        critique_text = " | ".join(critique_lines[:4]) if critique_lines else _normalize_inline_text(result.review_critique)
        specs.append(
            (
                "failure_constraint",
                "review",
                f"Do not ship a report that still violates reviewer expectations. {critique_text or 'Major reviewer issues remained unresolved.'}",
                "Resolve all visible major reviewer concerns in one pass before treating the report as complete.",
            )
        )
        specs.append(
            (
                "failure_checklist",
                "review",
                "Checklist before finishing: verify artifact paths, keep interpretation non-causal, and ensure any reviewer-blocking issue has been explicitly addressed.",
                "Run a final self-check against reviewer critiques and artifact paths before finish.",
            )
        )

    if not result.workflow_complete:
        specs.append(
            (
                "failure_checklist",
                "finalize",
                "Do not treat a run as complete when the artifact contract is still broken.",
                "Before ending the run, verify cleaned data, final report, trace, and stage audit all pass together.",
            )
        )
    return tuple(dict.fromkeys(specs))


def _build_analysis_summary(result: AnalysisRunResult) -> str:
    section_snippets: list[str] = []
    for title, body in _iter_markdown_sections(result.report_markdown):
        if title.strip().lower() not in {
            "result interpretation",
            "discussion",
            "conclusion",
            "缁撴灉瑙ｉ噴",
            "璁ㄨ",
            "缁撹",
        }:
            continue
        normalized = _normalize_inline_text(body)
        if normalized:
            section_snippets.append(f"{title.strip()}: {normalized[:180]}")
        if len(section_snippets) >= 2:
            break
    section_text = " | ".join(section_snippets) if section_snippets else _normalize_inline_text(result.report_markdown)[:260]
    pdf_hint = (
        f" Primary table: {result.selected_table_id}."
        if result.input_kind == "pdf" and result.selected_table_id
        else ""
    )
    methods = ", ".join(result.methods_used[:4]) if result.methods_used else "domain-specific descriptive workflow"
    return (
        f"Accepted {result.quality_mode} analysis for {result.detected_domain or 'unknown'} used {methods}."
        f"{pdf_hint} Key takeaways: {section_text}"
    ).strip()


def _build_user_preference(result: AnalysisRunResult) -> str:
    preference_bits = [
        f"Prefer {result.quality_mode} quality output",
        "preserve cautious, non-causal interpretation",
    ]
    if result.rag_enabled:
        preference_bits.append("keep retrieved knowledge explanations citation-backed when used")
    if result.input_kind == "pdf":
        preference_bits.append("treat the selected primary table as the formal quantitative basis")
    return "; ".join(preference_bits) + "."


def _build_review_constraint(result: AnalysisRunResult, review_history: tuple[ReviewRecord, ...]) -> str:
    lessons: list[str] = []
    for review in review_history:
        if review.decision != "Reject":
            continue
        lessons.extend(_extract_actionable_review_lines(review.critique))
        for finding in review.evidence_findings:
            message = _normalize_inline_text(finding.message)
            if message:
                lessons.append(message)
    if not lessons:
        lessons.extend(
            [
                "Keep artifact paths and generated figure references consistent with the trace",
                "Do not overstate causal claims or unsupported quantitative inference",
            ]
        )
        if result.rag_enabled:
            lessons.append("Use valid inline citations for retrieved knowledge-based explanations")
    unique_lessons = tuple(dict.fromkeys(item for item in lessons if item))
    return "Reviewer-aligned constraints: " + " | ".join(unique_lessons[:4]) + "."


def _build_rag_usage_note(result: AnalysisRunResult, source_names: tuple[str, ...]) -> str:
    if not result.rag_enabled or not source_names:
        return ""
    source_text = ", ".join(source_names[:4])
    return (
        f"Useful background sources in this project included {source_text}. "
        f"Evidence coverage status was {result.rag_evidence_coverage_status}; keep domain explanations aligned with those sources."
    )


def _extract_actionable_review_lines(text: str) -> tuple[str, ...]:
    lines: list[str] = []
    for raw_line in re.split(r"[\r\n]+", str(text or "")):
        cleaned = re.sub(r"^\s*(\d+[\.\)]|[-*])\s*", "", raw_line).strip()
        cleaned = _normalize_inline_text(cleaned)
        if cleaned:
            lines.append(cleaned)
    return tuple(lines[:4])


def _normalize_inline_text(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def _distill_record_texts_with_llm(
    *,
    llm: Any,
    result: AnalysisRunResult,
    review_history: tuple[ReviewRecord, ...],
    record_specs: tuple[tuple[str, str], ...],
) -> dict[str, str]:
    current = {memory_type: text for memory_type, text in record_specs}
    prompt = (
        "You are distilling compact project memory for a data-analysis agent.\n"
        "Rewrite each provided memory field into one short, stable, reusable sentence or two.\n"
        "Do not invent facts. Preserve reviewer constraints and user preferences.\n"
        "Return exactly one JSON object with optional keys: analysis_summary, user_preference, review_constraint, rag_usage_note.\n\n"
        f"Detected domain: {result.detected_domain}\n"
        f"Quality mode: {result.quality_mode}\n"
        f"Review status: {result.review_status}\n"
        f"Existing draft memory: {json.dumps(current, ensure_ascii=False)}\n"
        f"Review critique snippets: {json.dumps([review.critique for review in review_history], ensure_ascii=False)}\n"
    )
    response = str(llm.invoke([{"role": "user", "content": prompt}])).strip()
    match = re.search(r"\{[\s\S]*\}", response)
    payload = json.loads(match.group(0) if match else response)
    if not isinstance(payload, dict):
        return {}
    return {str(key): _normalize_inline_text(value) for key, value in payload.items() if _normalize_inline_text(value)}
