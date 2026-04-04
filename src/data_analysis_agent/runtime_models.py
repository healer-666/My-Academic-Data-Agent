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
    tool_status: str = "unknown"
    observation: Optional[str] = None
    observation_preview: str = ""
    summary: str = ""
    parse_error: Optional[str] = None
    llm_duration_ms: int = 0
    tool_duration_ms: int = 0


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


@dataclass(frozen=True)
class ArtifactValidationResult:
    workflow_complete: bool
    missing_artifacts: tuple[str, ...]
    warnings: tuple[str, ...]
    cleaned_data_exists: bool
    report_exists: bool
    trace_exists: bool


@dataclass(frozen=True)
class ReviewRecord:
    round_index: int
    decision: str
    critique: str
    raw_response: str
    review_log_path: Path
    candidate_report_path: Path


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
    total_duration_ms: int = 0
    llm_duration_ms: int = 0
    tool_duration_ms: int = 0
    review_duration_ms: int = 0
    timing_breakdown: dict[str, int] = field(default_factory=dict)
