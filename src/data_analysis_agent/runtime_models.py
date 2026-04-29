"""Shared runtime data models for workflow, events, and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .data_context import DataContextSummary
from .reporting import ReportTelemetry


class WorkflowState(str, Enum):
    INGEST = "ingest"
    CONTEXT = "context"
    ANALYZE_ROUND = "analyze_round"
    VALIDATE = "validate"
    REVIEW = "review"
    FINALIZE = "finalize"


@dataclass(frozen=True)
class RunContext:
    run_id: str
    session_id: str
    source_path: Path
    output_root: Path
    run_dir: Path
    data_dir: Path
    figures_dir: Path
    logs_dir: Path
    cleaned_data_path: Path
    report_path: Path
    trace_path: Path
    quality_mode: str
    latency_mode: str
    vision_review_mode: str
    document_ingestion_mode: str
    selected_table_id: str = ""

    def build_run_context_text(self, *, figures_dir: Path | None = None) -> str:
        active_figures_dir = figures_dir or self.figures_dir
        return (
            f"\n本次任务的专属输出根目录为：{self.run_dir.as_posix()}\n"
            f"清洗后的数据必须保存到：{self.cleaned_data_path.as_posix()}\n"
            f"所有图表必须保存到：{active_figures_dir.as_posix()}\n"
            f"运行轨迹与日志目录为：{self.logs_dir.as_posix()}\n"
            "请务必严格遵守“先清洗落盘，再重读分析”的两阶段流水线。\n"
        )


@dataclass(frozen=True)
class ToolExecutionRecord:
    tool_name: str
    tool_input: str
    tool_status: str
    observation: str
    observation_preview: str
    duration_ms: int


@dataclass(frozen=True)
class ModelCapability:
    role: str
    model_id: str
    base_url: str
    timeout: int
    configured: bool


@dataclass(frozen=True)
class AgentStepTrace:
    step_index: int
    raw_response: str
    action: str
    decision: str = ""
    tool_name: Optional[str] = None
    tool_input: str = ""
    tool_status: str = "unknown"
    observation: Optional[str] = None
    observation_preview: str = ""
    summary: str = ""
    parse_error: Optional[str] = None
    llm_duration_ms: int = 0
    tool_duration_ms: int = 0


@dataclass(frozen=True)
class StageExecutionFinding:
    finding_type: str
    message: str
    step_index: int | None = None
    rule_id: str = ""

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "type": self.finding_type,
            "message": self.message,
            "step_index": self.step_index,
            "rule_id": self.rule_id,
        }


@dataclass(frozen=True)
class StageExecutionAuditResult:
    status: str = "not_checked"
    stage1_save_detected: bool = False
    stage2_cleaned_reload_detected: bool = False
    raw_data_reused_after_stage1: bool = False
    findings: tuple[StageExecutionFinding, ...] = ()
    evidence_step_indices: tuple[int, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "passed": self.passed,
            "stage1_save_detected": self.stage1_save_detected,
            "stage2_cleaned_reload_detected": self.stage2_cleaned_reload_detected,
            "raw_data_reused_after_stage1": self.raw_data_reused_after_stage1,
            "findings": [finding.to_trace_dict() for finding in self.findings],
            "evidence_step_indices": list(self.evidence_step_indices),
        }


@dataclass(frozen=True)
class ReportContractCheckResult:
    passed: bool = True
    blocking_issues: tuple[str, ...] = ()
    section_presence: dict[str, bool] = field(default_factory=dict)
    figure_reference_count: int = 0
    figure_interpretation_hit_count: int = 0
    task_alignment_flags: dict[str, bool] = field(default_factory=dict)
    statistics_flags: dict[str, bool] = field(default_factory=dict)
    evidence_flags: dict[str, bool] = field(default_factory=dict)
    issue_types: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "blocking_issues": list(self.blocking_issues),
            "section_presence": dict(self.section_presence),
            "figure_reference_count": self.figure_reference_count,
            "figure_interpretation_hit_count": self.figure_interpretation_hit_count,
            "task_alignment_flags": dict(self.task_alignment_flags),
            "statistics_flags": dict(self.statistics_flags),
            "evidence_flags": dict(self.evidence_flags),
            "issue_types": list(self.issue_types),
            "rule_ids": list(self.rule_ids),
        }


@dataclass(frozen=True)
class RevisionBrief:
    source: str
    blocking_issues: tuple[str, ...] = ()
    suggested_actions: tuple[str, ...] = ()
    carry_over_constraints: tuple[str, ...] = ()
    next_round_figures_dir: str = ""

    def to_user_message(self) -> str:
        lines = [f"[Structured revision brief | source={self.source}]"]
        if self.blocking_issues:
            lines.append("Blocking issues:")
            lines.extend(f"{index}. {item}" for index, item in enumerate(self.blocking_issues, start=1))
        if self.suggested_actions:
            lines.append("Required actions:")
            lines.extend(f"- {item}" for item in self.suggested_actions)
        if self.carry_over_constraints:
            lines.append("Carry-over constraints:")
            lines.extend(f"- {item}" for item in self.carry_over_constraints)
        if self.next_round_figures_dir:
            lines.append(f"All new figures for the next round must be saved under: {self.next_round_figures_dir}")
        lines.append("Do not repeat any blocking issue that has already been called out.")
        return "\n".join(lines)


@dataclass(frozen=True)
class ParsedAgentReply:
    action: str
    decision: str
    tool_name: str = ""
    tool_input: str = ""
    final_answer: str = ""


@dataclass(frozen=True)
class ParsedReviewerReply:
    decision: str
    critique: str
    raw_response: str = ""
    evidence_findings: tuple["ReviewerEvidenceFinding", ...] = ()


@dataclass(frozen=True)
class ReviewerEvidenceFinding:
    finding_type: str
    message: str
    citation_label: str = ""


@dataclass(frozen=True)
class ArtifactValidationResult:
    workflow_complete: bool
    missing_artifacts: tuple[str, ...]
    warnings: tuple[str, ...]
    cleaned_data_exists: bool
    report_exists: bool
    trace_exists: bool
    stage_contract_status: str = "not_checked"
    stage_contract_findings: tuple[str, ...] = ()
    stage_contract_passed: bool = True


@dataclass(frozen=True)
class ReviewRecord:
    round_index: int
    decision: str
    critique: str
    raw_response: str
    review_log_path: Path
    candidate_report_path: Path
    evidence_findings: tuple[ReviewerEvidenceFinding, ...] = ()


@dataclass(frozen=True)
class VisualReviewRecord:
    round_index: int
    status: str
    decision: str
    summary: str
    figures_reviewed: tuple[str, ...]
    skipped_figures: tuple[str, ...]
    duration_ms: int
    raw_response: str
    warning: str
    log_path: Path


@dataclass(frozen=True)
class AnalystRoundRecord:
    round_index: int
    report_path: Path
    step_traces: tuple[AgentStepTrace, ...]
    execution_audit: StageExecutionAuditResult = StageExecutionAuditResult()
    report_contract_check: ReportContractCheckResult = ReportContractCheckResult()


@dataclass(frozen=True)
class AnalysisRunResult:
    data_context: DataContextSummary
    raw_result: str
    report_markdown: str
    report_path: Path
    output_dir: Path
    run_dir: Path
    data_dir: Path
    figures_dir: Path
    logs_dir: Path
    trace_path: Path
    cleaned_data_path: Path
    agent_type: str
    step_traces: tuple[AgentStepTrace, ...]
    telemetry: ReportTelemetry
    methods_used: tuple[str, ...]
    detected_domain: str
    tools_used: tuple[str, ...]
    search_status: str
    search_notes: str
    workflow_complete: bool
    workflow_warnings: tuple[str, ...]
    missing_artifacts: tuple[str, ...]
    quality_mode: str
    review_enabled: bool
    review_status: str
    review_rounds_used: int
    review_critique: str
    review_log_paths: tuple[Path, ...]
    symbolic_profile: str = "full"
    input_kind: str = "tabular"
    document_ingestion_status: str = "not_needed"
    document_ingestion_summary: str = ""
    document_ingestion_duration_ms: int = 0
    document_ingestion_log_path: Path | None = None
    candidate_table_count: int = 0
    selected_table_id: str = ""
    selected_table_shape: tuple[int, int] | None = None
    pdf_multi_table_mode: bool = False
    latency_mode: str = "auto"
    vision_review_mode: str = "auto"
    vision_review_enabled: bool = False
    vision_review_status: str = "skipped"
    vision_review_summary: str = ""
    vision_review_duration_ms: int = 0
    vision_review_log_paths: tuple[Path, ...] = ()
    rag_enabled: bool = False
    rag_status: str = "disabled"
    rag_match_count: int = 0
    rag_sources_used: tuple[str, ...] = ()
    rag_dense_match_count: int = 0
    rag_keyword_match_count: int = 0
    rag_retrieval_strategy: str = "dense_only"
    rag_table_candidate_count: int = 0
    rag_final_chunk_kinds: tuple[str, ...] = ()
    rag_selected_table_hit: bool = False
    rag_citation_count: int = 0
    rag_cited_sources: tuple[str, ...] = ()
    rag_evidence_coverage_status: str = "not_checked"
    rag_uncited_sections_detected: tuple[str, ...] = ()
    memory_enabled: bool = False
    memory_scope_key: str = ""
    memory_match_count: int = 0
    memory_writeback_status: str = "disabled"
    memory_written_count: int = 0
    failure_memory_enabled: bool = False
    failure_memory_match_count: int = 0
    failure_memory_writeback_status: str = "disabled"
    failure_memory_written_count: int = 0
    total_duration_ms: int = 0
    llm_duration_ms: int = 0
    tool_duration_ms: int = 0
    review_duration_ms: int = 0
    timing_breakdown: dict[str, int] = field(default_factory=dict)
    execution_audit_status: str = "not_checked"
    execution_audit_passed: bool = False
    execution_audit_findings: tuple[str, ...] = ()
    report_contract_passed: bool = False
    report_contract_blocking_issues: tuple[str, ...] = ()
    report_contract_issue_types: tuple[str, ...] = ()
