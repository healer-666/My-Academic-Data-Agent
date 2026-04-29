"""Custom agent runner and scientific ReAct controller."""

from __future__ import annotations

import contextlib
import io
import json
import re
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .artifact_service import (
    build_review_figures_dir as _build_review_figures_dir_service,
    build_run_context,
    build_run_context_text as _build_run_context_text_service,
    create_run_directory as _create_run_directory_service,
    reindex_step_traces as _reindex_step_traces_service,
    save_agent_trace as _save_agent_trace_service,
    save_run_summary as _save_run_summary_service,
    validate_artifacts as _validate_artifacts_service,
)
from .compat import ToolRegistry
from .config import RuntimeConfig, load_runtime_config
from .data_context import DataContextSummary, build_data_context
from .document_ingestion import IngestionResult
from .events import EventHandler, EventRecorder, emit_event
from .execution_audit import audit_stage_execution
from .harness.summary import build_run_summary_payload
from .knowledge_context import KnowledgeContextProvider
from .llm import build_llm
from .memory import (
    FailureMemoryService,
    ProjectMemoryService,
    derive_memory_scope_key,
    extract_failure_memory_records,
    extract_memory_records,
)
from .model_registry import ModelRegistry
from .prompts import (
    DEFAULT_QUERY,
    build_observation_prompt,
    build_reviewer_prompt,
    build_response_format_feedback,
    build_system_prompt,
)
from .report_contract import build_revision_brief, check_report_contract
from .rag import RagService
from .rag.models import RetrievedChunk
from .reporting import (
    analyze_evidence_coverage,
    ReportTelemetry,
    extract_report_and_telemetry,
    save_markdown_report,
)
from .review_service import (
    build_stage_audit_rejection as _build_stage_audit_rejection_service,
    build_reviewer_task as _build_reviewer_task_service,
    build_visual_review_summary as _build_visual_review_summary_service,
    default_max_reviews_for_mode as _default_max_reviews_for_mode_service,
    parse_reviewer_reply as _parse_reviewer_reply_service,
    safe_parse_reviewer_reply as _safe_parse_reviewer_reply_service,
    save_review_log as _save_review_log_service,
    save_visual_review_log as _save_visual_review_log_service,
    should_attempt_vision_review as _should_attempt_vision_review_service,
)
from .runtime_models import (
    AgentStepTrace,
    AnalysisRunResult,
    AnalystRoundRecord,
    ArtifactValidationResult,
    ParsedAgentReply,
    ParsedReviewerReply,
    ReportContractCheckResult,
    ReviewRecord,
    ReviewerEvidenceFinding,
    RevisionBrief,
    RunContext,
    StageExecutionAuditResult,
    VisualReviewRecord,
    WorkflowState,
)
from .symbolic_rules import get_symbolic_rules, resolve_symbolic_profile
from .tooling_service import (
    build_tool_registry as _build_tool_registry_service,
    collect_tools_used as _collect_tools_used_service,
    determine_search_status as _determine_search_status_service,
    execute_tool_call,
    parse_tool_observation as _parse_tool_observation_service,
)
from .vision_review import VisualReviewResult, run_visual_review
from .workflow_service import WorkflowTracker


def _emit_event(event_handler: Optional[EventHandler], event_type: str, **payload: Any) -> None:
    if event_handler is None:
        return
    bound_self = getattr(event_handler, "__self__", None)
    if bound_self is not None and isinstance(bound_self, EventRecorder):
        event_handler(event_type, **payload)
        return
    emit_event(event_handler, event_type, **payload)


def build_plaintext_event_handler() -> EventHandler:
    """Build a lightweight stdout event handler for notebooks and scripts."""

    def handle_event(event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "config_loading":
            print("[1/7] Loading runtime configuration...")
        elif event_type == "config_loaded":
            if payload.get("tavily_configured"):
                print(f"      Model: {payload.get('model_id', 'unknown')} | Tavily credential: detected")
            else:
                print(f"      Model: {payload.get('model_id', 'unknown')} | Tavily search: skipped unless configured")
            print(f"      Latency mode: {payload.get('latency_mode', 'auto')}")
            print(f"      Vision review: {'configured' if payload.get('vision_configured') else 'not configured'}")
        elif event_type == "run_directory_created":
            print("[2/7] Created production run directory...")
            print(f"      Run root: {payload.get('run_dir', '')}")
        elif event_type == "document_ingestion_started":
            print("[3/7] Running input document ingestion...")
            print(f"      Input kind: {payload.get('input_kind', 'unknown')}")
        elif event_type == "document_ingestion_completed":
            print(f"      Document ingestion completed | status = {payload.get('status', 'unknown')}")
            print(f"      Summary: {payload.get('summary', '')}")
        elif event_type == "document_ingestion_skipped":
            print("      Document ingestion skipped: input is already tabular.")
        elif event_type == "data_context_loading":
            print("[4/7] Building compact dataset metadata context...")
        elif event_type == "data_context_ready":
            shape = payload.get("shape", ("?", "?"))
            print(f"      Data shape: {shape[0]} rows x {shape[1]} columns")
        elif event_type == "knowledge_indexing_started":
            print(f"      Indexing {payload.get('file_count', 0)} knowledge file(s) into the local knowledge base...")
        elif event_type == "knowledge_indexing_completed":
            print(
                f"      Knowledge indexing completed | status = {payload.get('status', 'unknown')} | "
                f"indexed = {payload.get('indexed_count', 0)}"
            )
        elif event_type == "knowledge_indexing_skipped":
            print(f"      Knowledge indexing skipped: {payload.get('reason', '')}")
        elif event_type == "knowledge_structured_chunking_completed":
            print(
                f"      Structured chunking completed | chunks = {payload.get('chunk_count', 0)} | "
                f"enabled = {payload.get('structured_chunking_enabled', False)}"
            )
        elif event_type == "knowledge_table_candidates_prepared":
            print(
                f"      PDF table candidates prepared | count = {payload.get('table_candidate_count', 0)} | "
                f"selected = {payload.get('selected_table_id', '')}"
            )
        elif event_type == "knowledge_retrieval_started":
            print("      Retrieving local background knowledge for this run...")
        elif event_type == "knowledge_query_built":
            print(
                f"      Retrieval query prepared | dense = {payload.get('dense_query', '')[:80]} | "
                f"keyword = {payload.get('keyword_query', '')[:80]}"
            )
        elif event_type == "knowledge_dense_retrieval_completed":
            print(f"      Dense retrieval completed | matches = {payload.get('match_count', 0)}")
        elif event_type == "knowledge_keyword_retrieval_completed":
            print(f"      Keyword retrieval completed | matches = {payload.get('match_count', 0)}")
        elif event_type == "knowledge_rerank_completed":
            print(
                f"      Hybrid rerank completed | final matches = {payload.get('match_count', 0)} | "
                f"strategy = {payload.get('retrieval_strategy', 'hybrid')}"
            )
        elif event_type == "knowledge_retrieval_completed":
            print(
                f"      Knowledge retrieval completed | status = {payload.get('status', 'unknown')} | "
                f"matches = {payload.get('match_count', 0)}"
            )
        elif event_type == "knowledge_retrieval_skipped":
            print(f"      Knowledge retrieval skipped: {payload.get('reason', '')}")
        elif event_type == "memory_retrieval_started":
            print(f"      Retrieving project memory | scope = {payload.get('scope_key', '')}")
        elif event_type == "memory_retrieval_completed":
            print(
                f"      Project memory retrieval completed | status = {payload.get('status', 'unknown')} | "
                f"matches = {payload.get('match_count', 0)}"
            )
        elif event_type == "memory_retrieval_skipped":
            print(f"      Project memory retrieval skipped: {payload.get('reason', '')}")
        elif event_type == "memory_writeback_started":
            print(f"      Writing accepted run into project memory | scope = {payload.get('scope_key', '')}")
        elif event_type == "memory_writeback_completed":
            print(
                f"      Project memory writeback completed | status = {payload.get('status', 'unknown')} | "
                f"written = {payload.get('written_count', 0)}"
            )
        elif event_type == "memory_writeback_skipped":
            print(f"      Project memory writeback skipped: {payload.get('reason', payload.get('status', ''))}")
        elif event_type == "tool_registry_ready":
            print(f"[5/7] Tool registry ready: {', '.join(payload.get('tools', []))}")
            print(
                f"      Fast path: {payload.get('fast_path_enabled', False)} | "
                f"effective max steps: {payload.get('effective_max_steps', '?')}"
            )
        elif event_type == "analysis_started":
            print(f"[6/7] {payload.get('agent_name', 'Agent')} started reasoning (max steps = {payload.get('max_steps', '?')})")
            if payload.get("analysis_round"):
                print(f"      Analysis round: {payload.get('analysis_round')}")
        elif event_type == "step_started":
            print(f"      Step {payload.get('step_index', '?')}/{payload.get('max_steps', '?')}: thinking...")
        elif event_type == "tool_call_started":
            tool_name = payload.get("tool_name", "UnknownTool")
            decision = payload.get("decision", "")
            print(f"      Calling {tool_name} | {decision}")
        elif event_type == "tool_call_completed":
            print(f"      Completed {payload.get('tool_name', 'UnknownTool')} | status = {payload.get('tool_status', 'unknown')}")
            preview = payload.get("observation_preview")
            if preview:
                print(f"        Observation: {preview}")
        elif event_type == "step_parse_error":
            print(f"      Protocol parse warning: {payload.get('message', '')}")
        elif event_type == "report_persisting":
            print("[7/7] Saving Markdown report and run trace...")
        elif event_type == "report_saved":
            print(f"      Final report: {payload.get('report_path', '')}")
            print(f"      Agent trace: {payload.get('trace_path', '')}")
        elif event_type == "artifact_validation_completed":
            if payload.get("workflow_complete"):
                print("[8/8] Production artifact validation passed.")
            else:
                print("[8/8] Production artifact validation failed.")
                print(f"      Missing: {', '.join(payload.get('missing_artifacts', []))}")
        elif event_type == "analysis_finished":
            print("      Final report generated successfully.")
        elif event_type == "analysis_max_steps":
            print("      Agent hit the max-step limit and returned a fallback report.")
        elif event_type == "vision_review_started":
            print(f"      Vision reviewer round {payload.get('review_round', '?')} started.")
        elif event_type == "vision_review_completed":
            print(
                f"      Vision reviewer completed | status = {payload.get('status', 'unknown')} | "
                f"decision = {payload.get('decision', 'unknown')}"
            )
        elif event_type == "vision_review_skipped":
            print(f"      Vision reviewer skipped: {payload.get('reason', '')}")
        elif event_type == "review_started":
            print(f"      Reviewer round {payload.get('review_round', '?')} started.")
        elif event_type == "review_rejected":
            print(f"      [REJECT] 审稿人意见：{payload.get('critique', '')}")
        elif event_type == "review_accepted":
            print("      [OK] 审稿通过：报告达到当前质量档位要求。")
        elif event_type == "review_max_reached":
            print("      Reviewer max rounds reached. Final report was not formally accepted.")

    return handle_event


def build_tool_registry(*, enable_search: bool = True) -> ToolRegistry:
    """Create the tool registry for the analysis agent."""
    return _build_tool_registry_service(enable_search=enable_search)


def _elapsed_ms(start_time: float) -> int:
    return int(round((time.perf_counter() - start_time) * 1000))


def _accumulate_duration(timing_breakdown: dict[str, int], key: str, duration_ms: int) -> None:
    timing_breakdown[key] = timing_breakdown.get(key, 0) + max(0, int(duration_ms))


def _truncate_text(text: str, limit: int) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + " ... [truncated]"


def _build_default_rag_payload(*, use_rag: bool, knowledge_base_dir: Path) -> dict[str, Any]:
    return {
        "enabled": bool(use_rag),
        "status": "disabled" if not use_rag else "skipped",
        "configured": False,
        "knowledge_base_dir": knowledge_base_dir.as_posix(),
        "collection_name": RagService.COLLECTION_NAME,
        "indexed_documents": [],
        "retrieval_query": "",
        "dense_query": "",
        "keyword_query": "",
        "dense_candidates": [],
        "keyword_candidates": [],
        "structured_chunking_enabled": True,
        "table_candidate_count": 0,
        "ephemeral_table_candidates": [],
        "merged_candidates_count": 0,
        "reranked_chunks": [],
        "retrieval_strategy": "hybrid",
        "retrieved_chunks": [],
        "final_chunk_kinds": [],
        "final_evidence_register": [],
        "citation_count": 0,
        "cited_evidence_ids": [],
        "cited_sources": [],
        "evidence_coverage_status": "not_checked",
        "uncited_sections_detected": [],
        "invalid_citation_labels": [],
        "warnings": [],
    }


def _build_default_memory_payload(*, use_memory: bool, memory_scope_key: str, memory_base_dir: Path) -> dict[str, Any]:
    return {
        "enabled": bool(use_memory),
        "scope_key": str(memory_scope_key or ""),
        "memory_base_dir": memory_base_dir.as_posix(),
        "configured": False,
        "status": "disabled" if not use_memory else "skipped",
        "retrieval_status": "disabled" if not use_memory else "skipped",
        "retrieval_query": "",
        "retrieved_records": [],
        "writeback_status": "disabled" if not use_memory else "skipped",
        "written_record_ids": [],
        "warnings": [],
    }


def _build_default_failure_memory_payload(*, use_memory: bool, memory_scope_key: str, memory_base_dir: Path) -> dict[str, Any]:
    return {
        "enabled": bool(use_memory),
        "scope_key": str(memory_scope_key or ""),
        "memory_base_dir": memory_base_dir.as_posix(),
        "configured": False,
        "status": "disabled" if not use_memory else "skipped",
        "retrieval_status": "disabled" if not use_memory else "skipped",
        "retrieval_query": "",
        "retrieved_records": [],
        "writeback_status": "disabled" if not use_memory else "skipped",
        "written_record_ids": [],
        "warnings": [],
    }


def _combine_memory_contexts(success_memory_context: str, failure_memory_context: str) -> str:
    parts: list[str] = []
    normalized_success = str(success_memory_context or "").strip()
    normalized_failure = str(failure_memory_context or "").strip()
    if normalized_success:
        parts.append(f"[Success Memory]\n{normalized_success}")
    if normalized_failure:
        parts.append(f"[Failure Memory]\n{normalized_failure}")
    return "\n\n".join(parts).strip()


def _build_tabular_ingestion_result(*, source_path: Path, logs_dir: Path) -> IngestionResult:
    log_path = logs_dir / "document_ingestion.json"
    payload = {
        "input_kind": "tabular",
        "status": "not_needed",
        "summary": "输入文件已经是结构化表格，已直接进入分析主链路。",
        "normalized_data_path": source_path.as_posix(),
        "duration_ms": 0,
        "candidate_table_count": 0,
        "pdf_multi_table_mode": False,
        "mode": "tabular_only",
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return IngestionResult(
        input_kind="tabular",
        status="not_needed",
        summary="输入文件已经是结构化表格，已直接进入分析主链路。",
        normalized_data_path=source_path,
        duration_ms=0,
        log_path=log_path,
        candidate_table_count=0,
        pdf_multi_table_mode=False,
    )


def _build_observation_summary(
    *,
    tool_name: str,
    observation: str,
    tool_status: str,
    observation_preview: str,
) -> str:
    try:
        payload = json.loads(observation)
    except Exception:
        return (
            f"Status: {tool_status}\n"
            f"Preview: {_truncate_text(observation_preview or observation, 300)}"
        )

    text = str(payload.get("text", "")).strip()
    data = payload.get("data", {})
    parts = [
        f"Status: {tool_status}",
        f"Preview: {_truncate_text(observation_preview or text, 300)}",
    ]

    if tool_name == "PythonInterpreterTool" and isinstance(data, dict):
        stdout_text = _truncate_text(str(data.get("stdout", "")).strip(), 1200)
        stderr_text = _truncate_text(str(data.get("stderr", "")).strip(), 800)
        warning_messages = data.get("warnings", [])
        if stdout_text:
            parts.append(f"Stdout:\n{stdout_text}")
        if stderr_text:
            parts.append(f"Stderr:\n{stderr_text}")
        if isinstance(warning_messages, list) and warning_messages:
            warnings_block = "\n".join(f"- {item}" for item in warning_messages[:5])
            if len(warning_messages) > 5:
                warnings_block += f"\n- ... {len(warning_messages) - 5} more warning(s) omitted."
            parts.append(f"Warnings:\n{warnings_block}")
        return "\n\n".join(parts)

    if tool_name == "TavilySearchTool" and isinstance(data, dict):
        query = str(data.get("query", "")).strip()
        results = data.get("results", [])
        if query:
            parts.append(f"Query: {query}")
        if isinstance(results, list) and results:
            result_lines = []
            for index, item in enumerate(results[:3], start=1):
                if not isinstance(item, dict):
                    continue
                title = _truncate_text(str(item.get("title", "Untitled")).strip(), 80)
                url = _truncate_text(str(item.get("url", "")).strip(), 120)
                snippet_source = item.get("content", item.get("snippet", ""))
                snippet = _truncate_text(str(snippet_source).strip(), 200)
                line = f"{index}. {title}"
                if url:
                    line += f" | {url}"
                if snippet:
                    line += f" | {snippet}"
                result_lines.append(line)
            if result_lines:
                parts.append("Top search results:\n" + "\n".join(result_lines))
            if len(results) > 3:
                parts.append(f"... {len(results) - 3} more result(s) omitted.")
        return "\n\n".join(parts)

    if text:
        parts.append(f"Observation text:\n{_truncate_text(text, 1200)}")
    return "\n\n".join(parts)


def _resolve_latency_mode(latency_mode: str) -> str:
    normalized_mode = latency_mode.strip().lower()
    if normalized_mode not in {"auto", "quality", "fast"}:
        raise ValueError(f"Unsupported latency_mode: {latency_mode}")
    return normalized_mode


def _resolve_vision_review_mode(vision_review_mode: str) -> str:
    normalized_mode = vision_review_mode.strip().lower()
    if normalized_mode not in {"off", "auto", "on"}:
        raise ValueError(f"Unsupported vision_review_mode: {vision_review_mode}")
    return normalized_mode


def _is_small_simple_dataset(data_context: DataContextSummary) -> bool:
    try:
        file_size_bytes = data_context.absolute_path.stat().st_size
    except OSError:
        file_size_bytes = 0
    rows, cols = data_context.shape
    return file_size_bytes <= 512 * 1024 and rows <= 2000 and cols <= 50


def _should_use_fast_path(latency_mode: str, *, small_simple_dataset: bool) -> bool:
    return latency_mode == "fast" or (latency_mode == "auto" and small_simple_dataset)


def _resolve_effective_max_steps(
    *,
    requested_max_steps: int,
    quality_mode: str,
    latency_mode: str,
    small_simple_dataset: bool,
) -> int:
    if not _should_use_fast_path(latency_mode, small_simple_dataset=small_simple_dataset):
        return requested_max_steps
    caps = {
        "draft": 3,
        "standard": 4,
        "publication": 5,
    }
    return min(requested_max_steps, caps[quality_mode])


_SEARCH_SIGNAL_KEYWORDS = (
    "clinical",
    "biomarker",
    "chromosome",
    "nipt",
    "cpi",
    "ppv",
    "odds ratio",
    "临床",
    "阈值",
    "正常范围",
    "染色体",
    "宏观",
    "统计口径",
)


def _should_enable_search(
    *,
    runtime_config: RuntimeConfig,
    data_context: DataContextSummary,
    query: str,
    quality_mode: str,
    latency_mode: str,
) -> bool:
    if not runtime_config.tavily_api_key:
        return False
    if latency_mode == "quality":
        return True

    searchable_text = " ".join([query, *data_context.columns])
    lowered = searchable_text.lower()
    if any(keyword in lowered for keyword in _SEARCH_SIGNAL_KEYWORDS):
        return True
    if re.search(r"\b[A-Z]{2,}[0-9A-Z/_-]*\b", searchable_text):
        return True
    return False


def _extract_first_json_object(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise ValueError("Model returned an empty response.")

    if stripped.startswith("```"):
        fence_lines = stripped.splitlines()
        if len(fence_lines) >= 3 and fence_lines[0].startswith("```") and fence_lines[-1].startswith("```"):
            stripped = "\n".join(fence_lines[1:-1]).strip()

    start = stripped.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model response.")

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(stripped)):
        char = stripped[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]

    raise ValueError("Unterminated JSON object in model response.")


def _parse_agent_reply(raw_response: str) -> ParsedAgentReply:
    json_payload = _extract_first_json_object(raw_response)

    try:
        payload = json.loads(json_payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON response: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Model response JSON must be an object.")

    action = str(payload.get("action", "")).strip().lower()
    if action not in {"call_tool", "finish"}:
        raise ValueError("Field 'action' must be either 'call_tool' or 'finish'.")

    decision = str(payload.get("decision", "")).strip()

    if action == "call_tool":
        tool_name = str(payload.get("tool_name", "")).strip()
        tool_input = str(payload.get("tool_input", "")).strip()
        if not tool_name:
            raise ValueError("Field 'tool_name' is required when action is 'call_tool'.")
        if not tool_input:
            raise ValueError("Field 'tool_input' is required when action is 'call_tool'.")
        return ParsedAgentReply(
            action=action,
            decision=decision,
            tool_name=tool_name,
            tool_input=tool_input,
            final_answer="",
        )

    final_answer = str(payload.get("final_answer", "")).strip()
    if not final_answer:
        raise ValueError("Field 'final_answer' is required when action is 'finish'.")

    return ParsedAgentReply(
        action=action,
        decision=decision,
        final_answer=final_answer,
    )


def _parse_reviewer_reply(raw_response: str) -> ParsedReviewerReply:
    return _parse_reviewer_reply_service(raw_response, _extract_first_json_object)


def _safe_parse_reviewer_reply(raw_response: str) -> ParsedReviewerReply:
    return _safe_parse_reviewer_reply_service(raw_response, _extract_first_json_object)


def _parse_tool_observation(observation: str) -> tuple[str, str]:
    return _parse_tool_observation_service(observation)


def _build_step_summary(tool_name: str, decision: str, tool_status: str, observation_preview: str) -> str:
    if tool_name == "TavilySearchTool":
        action_text = "Online domain knowledge retrieval"
    elif tool_name == "PythonInterpreterTool":
        action_text = "Local Python execution"
    else:
        action_text = f"Tool call: {tool_name}"

    summary = f"{action_text} | status={tool_status}"
    if decision:
        summary = f"{summary} | decision={decision}"
    if observation_preview:
        summary = f"{summary} | observation={observation_preview}"
    return summary


def _determine_search_status(step_traces: tuple[AgentStepTrace, ...], telemetry: ReportTelemetry) -> tuple[str, str]:
    return _determine_search_status_service(step_traces, telemetry)


def _collect_tools_used(step_traces: tuple[AgentStepTrace, ...], telemetry: ReportTelemetry) -> tuple[str, ...]:
    return _collect_tools_used_service(step_traces, telemetry)


def _create_run_directory(output_dir: str | Path) -> tuple[Path, Path, Path, Path]:
    return _create_run_directory_service(output_dir)


def _build_run_context_text(run_dir: Path, cleaned_data_path: Path, figures_dir: Path, logs_dir: Path) -> str:
    return (
        f"\n本次任务的专属输出根目录为：{run_dir.as_posix()}\n"
        f"清洗后的数据必须保存到：{cleaned_data_path.as_posix()}\n"
        f"所有图表必须保存到：{figures_dir.as_posix()}\n"
        f"运行轨迹与日志目录为：{logs_dir.as_posix()}\n"
        "请务必严格遵守“先清洗落盘，再重读分析”的两阶段流水线。\n"
    )


def _resolve_quality_mode(quality_mode: str) -> str:
    normalized_mode = quality_mode.strip().lower()
    if normalized_mode not in {"draft", "standard", "publication"}:
        raise ValueError(f"Unsupported quality_mode: {quality_mode}")
    return normalized_mode


def _should_attempt_vision_review(*, quality_mode: str, review_enabled: bool, vision_review_mode: str) -> bool:
    if not review_enabled or vision_review_mode == "off":
        return False
    if vision_review_mode == "on":
        return quality_mode in {"standard", "publication"}
    return quality_mode == "publication"


def _default_max_reviews_for_mode(quality_mode: str) -> int:
    mapping = {
        "draft": 0,
        "standard": 1,
        "publication": 2,
    }
    return mapping[quality_mode]


def _build_review_figures_dir(figures_root: Path, review_round: int) -> Path:
    review_figures_dir = figures_root / f"review_round_{review_round}"
    review_figures_dir.mkdir(parents=True, exist_ok=True)
    return review_figures_dir


def _serialize_step_traces(step_traces: tuple[AgentStepTrace, ...]) -> list[dict[str, Any]]:
    return [asdict(trace) for trace in step_traces]


def _reindex_step_traces(step_traces: list[AgentStepTrace], start_index: int) -> tuple[AgentStepTrace, ...]:
    return tuple(
        AgentStepTrace(
            step_index=start_index + offset,
            raw_response=trace.raw_response,
            action=trace.action,
            decision=trace.decision,
            tool_name=trace.tool_name,
            tool_input=trace.tool_input,
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


def _serialize_analysis_rounds(rounds: tuple[AnalystRoundRecord, ...]) -> list[dict[str, Any]]:
    return [
        {
            "round_index": round_record.round_index,
            "report_path": round_record.report_path.as_posix(),
            "step_traces": _serialize_step_traces(round_record.step_traces),
            "execution_audit": round_record.execution_audit.to_trace_dict(),
        }
        for round_record in rounds
    ]


def _serialize_review_history(review_history: tuple[ReviewRecord, ...]) -> list[dict[str, Any]]:
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


def _serialize_visual_review_history(visual_review_history: tuple[VisualReviewRecord, ...]) -> list[dict[str, Any]]:
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


def _build_visual_review_summary(review: VisualReviewResult) -> str:
    return _build_visual_review_summary_service(review)


def _build_stage_audit_rejection(audit_result: StageExecutionAuditResult) -> ParsedReviewerReply:
    return _build_stage_audit_rejection_service(audit_result)


def _can_reuse_prior_passed_execution_audit(audit_result: StageExecutionAuditResult) -> bool:
    if audit_result.passed:
        return False
    return audit_result.status == "skipped" and any(
        "No successful Python analysis steps were available" in finding.message for finding in audit_result.findings
    )


def _select_effective_execution_audit(
    audit_result: StageExecutionAuditResult,
    prior_rounds: tuple[AnalystRoundRecord, ...],
) -> StageExecutionAuditResult:
    if not _can_reuse_prior_passed_execution_audit(audit_result):
        return audit_result
    for prior_round in reversed(prior_rounds):
        if prior_round.execution_audit.passed:
            return prior_round.execution_audit
    return audit_result


def _extract_blocking_issues_from_critique(critique: str) -> tuple[str, ...]:
    text = str(critique or "").strip()
    if not text:
        return ()
    issues: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^\d+[\.\)]\s*", "", stripped)
        stripped = re.sub(r"^[-*]\s*", "", stripped)
        if stripped:
            issues.append(stripped)
    if not issues:
        issues.append(text)
    return tuple(dict.fromkeys(issues))


def _build_reviewer_task(
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
    evidence_coverage=None,
    memory_context: str = "",
    execution_audit: StageExecutionAuditResult | None = None,
    report_contract_check: ReportContractCheckResult | None = None,
    task_type: str = "",
    task_expectations: tuple[str, ...] = (),
) -> str:
    return _build_reviewer_task_service(
        data_context=data_context,
        report_markdown=report_markdown,
        report_path=report_path,
        step_traces=step_traces,
        artifact_validation=artifact_validation,
        telemetry=telemetry,
        review_round=review_round,
        visual_review_summary=visual_review_summary,
        evidence_register=evidence_register,
        evidence_coverage=evidence_coverage,
        memory_context=memory_context,
        execution_audit=execution_audit,
        report_contract_check=report_contract_check,
        task_type=task_type,
        task_expectations=task_expectations,
    )


def _save_review_log(
    *,
    review_log_path: Path,
    review_round: int,
    reviewer_reply: ParsedReviewerReply,
    candidate_report_path: Path,
) -> Path:
    return _save_review_log_service(
        review_log_path=review_log_path,
        review_round=review_round,
        reviewer_reply=reviewer_reply,
        candidate_report_path=candidate_report_path,
    )


def _save_visual_review_log(
    *,
    review_log_path: Path,
    review_round: int,
    reviewer_reply: VisualReviewResult,
) -> Path:
    return _save_visual_review_log_service(
        review_log_path=review_log_path,
        review_round=review_round,
        reviewer_reply=reviewer_reply,
    )


def _save_agent_trace(
    *,
    trace_path: Path,
    runtime_config: RuntimeConfig,
    data_context: DataContextSummary,
    run_dir: Path,
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
    quality_mode: str,
    latency_mode: str,
    vision_review_mode: str,
    review_enabled: bool,
    search_enabled: bool,
    fast_path_enabled: bool,
    small_simple_dataset: bool,
    vision_configured: bool,
    timing_breakdown: dict[str, int],
    run_context: RunContext | None = None,
    workflow_states: tuple[WorkflowState, ...] = (),
    event_stream: tuple[Any, ...] = (),
    rag_payload: dict[str, Any] | None = None,
    memory_payload: dict[str, Any] | None = None,
    failure_memory_payload: dict[str, Any] | None = None,
    execution_audit: StageExecutionAuditResult | None = None,
    report_contract_check: ReportContractCheckResult | None = None,
    symbolic_profile: str = "full",
) -> Path:
    active_run_context = run_context or RunContext(
        run_id=run_dir.name,
        session_id=run_dir.name,
        source_path=data_context.absolute_path,
        output_root=run_dir.parent,
        run_dir=run_dir,
        data_dir=run_dir / "data",
        figures_dir=run_dir / "figures",
        logs_dir=run_dir / "logs",
        cleaned_data_path=run_dir / "data" / "cleaned_data.csv",
        report_path=run_dir / "final_report.md",
        trace_path=trace_path,
        quality_mode=quality_mode,
        latency_mode=latency_mode,
        vision_review_mode=vision_review_mode,
        document_ingestion_mode="unknown",
    )
    return _save_agent_trace_service(
        trace_path=trace_path,
        runtime_config=runtime_config,
        data_context=data_context,
        run_context=active_run_context,
        max_steps=max_steps,
        effective_max_steps=effective_max_steps,
        step_traces=step_traces,
        telemetry=telemetry,
        search_status=search_status,
        search_notes=search_notes,
        tools_used=tools_used,
        artifact_validation=artifact_validation,
        analysis_rounds=analysis_rounds,
        review_history=review_history,
        visual_review_history=visual_review_history,
        document_ingestion=document_ingestion,
        review_status=review_status,
        review_enabled=review_enabled,
        search_enabled=search_enabled,
        fast_path_enabled=fast_path_enabled,
        small_simple_dataset=small_simple_dataset,
        vision_configured=vision_configured,
        timing_breakdown=timing_breakdown,
        workflow_states=workflow_states,
        event_stream=event_stream,
        rag_payload=rag_payload,
        memory_payload=memory_payload,
        failure_memory_payload=failure_memory_payload,
        execution_audit=execution_audit,
        report_contract_check=report_contract_check,
        symbolic_profile=symbolic_profile,
        symbolic_rules=get_symbolic_rules(),
    )


def _validate_artifacts(
    *,
    cleaned_data_path: Path,
    report_path: Path,
    trace_path: Path,
    telemetry: ReportTelemetry,
    execution_audit: StageExecutionAuditResult | None = None,
) -> ArtifactValidationResult:
    return _validate_artifacts_service(
        cleaned_data_path=cleaned_data_path,
        report_path=report_path,
        trace_path=trace_path,
        telemetry=telemetry,
        execution_audit=execution_audit,
    )


class ScientificReActRunner:
    """Custom JSON-driven ReAct controller for scientific analysis tasks."""

    def __init__(
        self,
        *,
        name: str,
        llm: Any,
        system_prompt: str,
        tool_registry: Any,
        max_steps: int = 6,
        fast_path_enabled: bool = False,
        event_handler: Optional[EventHandler] = None,
    ) -> None:
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.tool_registry = tool_registry
        self.max_steps = max_steps
        self.fast_path_enabled = fast_path_enabled
        self.event_handler = event_handler

    def build_initial_messages(self, user_task: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_task},
        ]

    def run(self, user_task: str) -> tuple[str, list[AgentStepTrace]]:
        final_answer, traces, _ = self.run_with_messages(self.build_initial_messages(user_task))
        return final_answer, traces

    def run_with_messages(
        self,
        messages: list[dict[str, str]],
        *,
        analysis_round: int = 1,
    ) -> tuple[str, list[AgentStepTrace], list[dict[str, str]]]:
        messages = list(messages)
        traces: list[AgentStepTrace] = []
        available_tools = set(self.tool_registry.list_tools())

        _emit_event(
            self.event_handler,
            "analysis_started",
            agent_name=self.name,
            max_steps=self.max_steps,
            analysis_round=analysis_round,
        )

        for step_index in range(1, self.max_steps + 1):
            _emit_event(self.event_handler, "step_started", step_index=step_index, max_steps=self.max_steps)
            llm_started_at = time.perf_counter()
            raw_response = str(self.llm.invoke(messages)).strip()
            llm_duration_ms = _elapsed_ms(llm_started_at)

            try:
                reply = _parse_agent_reply(raw_response)
            except ValueError as exc:
                parse_error = str(exc)
                trace = AgentStepTrace(
                    step_index=step_index,
                    raw_response=raw_response,
                    action="parse_error",
                    tool_status="error",
                    summary=f"Model response failed JSON validation: {parse_error}",
                    parse_error=parse_error,
                    llm_duration_ms=llm_duration_ms,
                )
                traces.append(trace)
                _emit_event(
                    self.event_handler,
                    "step_parse_error",
                    step_index=step_index,
                    message=parse_error,
                )
                messages.append({"role": "assistant", "content": raw_response})
                messages.append({"role": "user", "content": build_response_format_feedback(parse_error)})
                continue

            if reply.action == "call_tool":
                _emit_event(
                    self.event_handler,
                    "tool_call_started",
                    step_index=step_index,
                    tool_name=reply.tool_name,
                    decision=reply.decision,
                )

                tool_execution = execute_tool_call(
                    tool_registry=self.tool_registry,
                    tool_name=reply.tool_name,
                    tool_input=reply.tool_input,
                    available_tools=available_tools,
                )
                observation = tool_execution.observation
                tool_duration_ms = tool_execution.duration_ms
                tool_status = tool_execution.tool_status
                observation_preview = tool_execution.observation_preview
                observation_summary = _build_observation_summary(
                    tool_name=reply.tool_name,
                    observation=observation,
                    tool_status=tool_status,
                    observation_preview=observation_preview,
                )
                trace = AgentStepTrace(
                    step_index=step_index,
                    raw_response=raw_response,
                    action=reply.action,
                    decision=reply.decision,
                    tool_name=reply.tool_name,
                    tool_input=reply.tool_input if reply.tool_name == "PythonInterpreterTool" else "",
                    tool_status=tool_status,
                    observation=observation,
                    observation_preview=observation_preview,
                    summary=_build_step_summary(reply.tool_name, reply.decision, tool_status, observation_preview),
                    llm_duration_ms=llm_duration_ms,
                    tool_duration_ms=tool_duration_ms,
                )
                traces.append(trace)

                _emit_event(
                    self.event_handler,
                    "tool_call_completed",
                    step_index=step_index,
                    tool_name=reply.tool_name,
                    decision=reply.decision,
                    tool_status=tool_status,
                    observation_preview=observation_preview,
                    summary=trace.summary,
                    llm_duration_ms=llm_duration_ms,
                    tool_duration_ms=tool_duration_ms,
                )

                messages.append({"role": "assistant", "content": raw_response})
                messages.append(
                    {
                        "role": "user",
                        "content": build_observation_prompt(
                            tool_name=reply.tool_name,
                            observation_summary=observation_summary,
                            remaining_steps=self.max_steps - step_index,
                            fast_path_enabled=self.fast_path_enabled,
                        ),
                    }
                )
                continue

            trace = AgentStepTrace(
                step_index=step_index,
                raw_response=raw_response,
                action=reply.action,
                decision=reply.decision,
                tool_status="success",
                summary=f"Generated final Markdown report: {reply.decision or 'analysis complete'}",
                llm_duration_ms=llm_duration_ms,
            )
            traces.append(trace)
            _emit_event(
                self.event_handler,
                "analysis_finished",
                step_index=step_index,
                decision=reply.decision,
            )
            messages.append({"role": "assistant", "content": raw_response})
            return reply.final_answer, traces, messages

        fallback_report = (
            "# Data Analysis Report\n\n"
            "The agent reached the maximum number of reasoning steps before producing a final report.\n\n"
            "## Next Action\n"
            "Please review the step traces to identify whether the issue came from response formatting, "
            "tool execution errors, or insufficient statistical instructions.\n\n"
            "<telemetry>{\"methods\": [], \"domain\": \"unknown\", \"tools_used\": [], "
            "\"search_used\": false, \"search_notes\": \"Agent reached max steps before finalizing.\", "
            "\"cleaned_data_saved\": false, \"cleaned_data_path\": \"\", \"figures_generated\": []}</telemetry>"
        )
        _emit_event(self.event_handler, "analysis_max_steps", max_steps=self.max_steps)
        return fallback_report, traces, messages


def run_analysis(
    data_path: str | Path,
    *,
    query: str = DEFAULT_QUERY,
    output_dir: str | Path = "outputs",
    report_path: Optional[str | Path] = None,
    env_file: Optional[str | Path] = None,
    agent_name: str = "Advanced Data Analyst",
    max_steps: int = 6,
    max_reviews: Optional[int] = None,
    quality_mode: str = "standard",
    latency_mode: str = "auto",
    vision_review_mode: str = "auto",
    vision_max_images: int = 3,
    vision_max_image_side: int = 1024,
    event_handler: Optional[EventHandler] = None,
    verbose: bool = False,
    use_rag: bool = True,
    knowledge_paths: Iterable[str | Path] = (),
    knowledge_base_dir: str | Path | None = None,
    use_memory: bool = True,
    memory_scope_key: str | None = None,
    task_type: str = "",
    task_expectations: Iterable[str] = (),
    symbolic_profile: str = "full",
) -> AnalysisRunResult:
    """Run the full data analysis workflow."""

    if event_handler is None and verbose:
        event_handler = build_plaintext_event_handler()

    event_recorder = EventRecorder(event_handler)
    workflow_tracker = WorkflowTracker(event_recorder)

    run_started_at = time.perf_counter()
    timing_breakdown: dict[str, int] = {}

    _emit_event(event_recorder.emit, "config_loading")
    config_started_at = time.perf_counter()
    runtime_config: RuntimeConfig = load_runtime_config(env_file=env_file)
    _accumulate_duration(timing_breakdown, "config_load_duration_ms", _elapsed_ms(config_started_at))

    resolved_quality_mode = _resolve_quality_mode(quality_mode)
    resolved_latency_mode = _resolve_latency_mode(latency_mode)
    resolved_vision_review_mode = _resolve_vision_review_mode(vision_review_mode)
    resolved_symbolic_profile = resolve_symbolic_profile(symbolic_profile)
    review_enabled = resolved_quality_mode != "draft" and resolved_symbolic_profile == "full"
    effective_max_reviews = (
        _default_max_reviews_for_mode(resolved_quality_mode) if max_reviews is None else max(0, max_reviews)
    )
    if not review_enabled:
        effective_max_reviews = 0

    model_registry = ModelRegistry.from_runtime_config(runtime_config)

    _emit_event(
        event_recorder.emit,
        "config_loaded",
        tavily_configured=bool(runtime_config.tavily_api_key),
        embedding_configured=runtime_config.embedding_configured,
        vision_configured=runtime_config.vision_configured,
        model_id=runtime_config.model_id,
        latency_mode=resolved_latency_mode,
        search_enabled=bool(runtime_config.tavily_api_key),
    )

    source_path = Path(data_path).resolve()
    resolved_task_type = str(task_type or "").strip()
    resolved_task_expectations = tuple(str(item).strip() for item in task_expectations if str(item).strip())
    resolved_memory_scope_key = derive_memory_scope_key(
        explicit_scope_key=memory_scope_key,
        source_path=source_path,
    )
    run_context = build_run_context(
        source_path=source_path,
        output_dir=output_dir,
        quality_mode=resolved_quality_mode,
        latency_mode=resolved_latency_mode,
        vision_review_mode=resolved_vision_review_mode,
        document_ingestion_mode="tabular_only",
        run_dir_parts=_create_run_directory(output_dir),
    )
    run_dir = run_context.run_dir
    data_dir = run_context.data_dir
    figures_dir = run_context.figures_dir
    logs_dir = run_context.logs_dir
    cleaned_data_path = run_context.cleaned_data_path
    final_report_path = run_context.report_path
    trace_path = run_context.trace_path
    _emit_event(
        event_recorder.emit,
        "run_directory_created",
        run_dir=run_dir.as_posix(),
        data_dir=data_dir.as_posix(),
        figures_dir=figures_dir.as_posix(),
        logs_dir=logs_dir.as_posix(),
    )

    supported_suffixes = {".csv", ".xls", ".xlsx"}
    if source_path.suffix.lower() not in supported_suffixes:
        raise ValueError(
            f"Unsupported input file format: {source_path.suffix}. "
            "当前版本仅支持 CSV / XLS / XLSX 结构化表格数据。"
        )
    input_kind = "tabular"
    workflow_tracker.transition(WorkflowState.INGEST)
    _emit_event(
        event_recorder.emit,
        "document_ingestion_started",
        input_kind=input_kind,
        data_path=source_path.as_posix(),
    )
    ingestion_started_at = time.perf_counter()
    document_ingestion = _build_tabular_ingestion_result(
        source_path=source_path,
        logs_dir=logs_dir,
    )
    _accumulate_duration(
        timing_breakdown,
        "document_ingestion_duration_ms",
        max(document_ingestion.duration_ms, _elapsed_ms(ingestion_started_at)),
    )
    _emit_event(event_recorder.emit, "document_ingestion_skipped")

    workflow_tracker.transition(WorkflowState.CONTEXT)
    _emit_event(event_recorder.emit, "data_context_loading", data_path=document_ingestion.normalized_data_path.as_posix())
    data_context_started_at = time.perf_counter()
    data_context = build_data_context(
        document_ingestion.normalized_data_path,
        input_kind=document_ingestion.input_kind,
    )
    _accumulate_duration(timing_breakdown, "data_context_duration_ms", _elapsed_ms(data_context_started_at))
    small_simple_dataset = _is_small_simple_dataset(data_context)
    fast_path_enabled = _should_use_fast_path(resolved_latency_mode, small_simple_dataset=small_simple_dataset)
    effective_max_steps = _resolve_effective_max_steps(
        requested_max_steps=max_steps,
        quality_mode=resolved_quality_mode,
        latency_mode=resolved_latency_mode,
        small_simple_dataset=small_simple_dataset,
    )
    search_enabled = _should_enable_search(
        runtime_config=runtime_config,
        data_context=data_context,
        query=query,
        quality_mode=resolved_quality_mode,
        latency_mode=resolved_latency_mode,
    )
    _emit_event(
        event_recorder.emit,
        "data_context_ready",
        data_path=data_context.absolute_path.as_posix(),
        shape=data_context.shape,
        columns=data_context.columns,
        small_simple_dataset=small_simple_dataset,
    )

    knowledge_provider = KnowledgeContextProvider()
    active_knowledge_base_dir = Path(knowledge_base_dir or Path("memory") / "knowledge_base").resolve()
    active_memory_base_dir = (Path("memory") / "project_memory").resolve()
    active_failure_memory_base_dir = (Path("memory") / "failure_memory").resolve()
    rag_payload = _build_default_rag_payload(use_rag=use_rag, knowledge_base_dir=active_knowledge_base_dir)
    rag_payload["configured"] = runtime_config.embedding_configured
    memory_payload = _build_default_memory_payload(
        use_memory=use_memory,
        memory_scope_key=resolved_memory_scope_key,
        memory_base_dir=active_memory_base_dir,
    )
    memory_payload["configured"] = runtime_config.embedding_configured
    failure_memory_payload = _build_default_failure_memory_payload(
        use_memory=use_memory,
        memory_scope_key=resolved_memory_scope_key,
        memory_base_dir=active_failure_memory_base_dir,
    )
    failure_memory_payload["configured"] = runtime_config.embedding_configured
    rag_status = str(rag_payload["status"])
    rag_match_count = 0
    rag_dense_match_count = 0
    rag_keyword_match_count = 0
    rag_sources_used: tuple[str, ...] = ()
    rag_retrieval_strategy = "hybrid"
    rag_table_candidate_count = 0
    rag_final_chunk_kinds: tuple[str, ...] = ()
    rag_selected_table_hit = False
    rag_citation_count = 0
    rag_cited_sources: tuple[str, ...] = ()
    rag_evidence_coverage_status = "not_checked"
    rag_uncited_sections_detected: tuple[str, ...] = ()
    current_evidence_register: tuple[RetrievedChunk, ...] = ()
    memory_match_count = 0
    memory_writeback_status = "disabled" if not use_memory else "skipped"
    memory_written_count = 0
    failure_memory_match_count = 0
    failure_memory_writeback_status = "disabled" if not use_memory else "skipped"
    failure_memory_written_count = 0
    success_memory_context_text = ""
    failure_memory_context_text = ""
    combined_memory_context_text = ""
    memory_records = ()
    failure_memory_records = ()
    if knowledge_paths is None:
        knowledge_path_items = ()
    elif isinstance(knowledge_paths, (str, Path)):
        knowledge_path_items: tuple[str | Path, ...] = (knowledge_paths,)
    else:
        knowledge_path_items = tuple(knowledge_paths)
    normalized_knowledge_paths = tuple(
        Path(path)
        for path in knowledge_path_items
        if str(path or "").strip()
    )
    rag_payload["knowledge_paths"] = [path.resolve().as_posix() for path in normalized_knowledge_paths]
    if not use_memory:
        memory_payload["status"] = "disabled"
        memory_payload["retrieval_status"] = "disabled"
        failure_memory_payload["status"] = "disabled"
        failure_memory_payload["retrieval_status"] = "disabled"
        _emit_event(
            event_recorder.emit,
            "memory_retrieval_skipped",
            status="disabled",
            reason="Memory is disabled for this run.",
        )
        _emit_event(
            event_recorder.emit,
            "failure_memory_retrieval_skipped",
            status="disabled",
            reason="Failure memory is disabled for this run.",
        )
    elif not runtime_config.embedding_configured:
        memory_payload["status"] = "skipped"
        memory_payload["retrieval_status"] = "skipped"
        memory_payload["warnings"].append("Embedding configuration is incomplete; skipping project memory retrieval.")
        failure_memory_payload["status"] = "skipped"
        failure_memory_payload["retrieval_status"] = "skipped"
        failure_memory_payload["warnings"].append("Embedding configuration is incomplete; skipping failure memory retrieval.")
        _emit_event(
            event_recorder.emit,
            "memory_retrieval_skipped",
            status="skipped",
            reason="Embedding configuration is incomplete; skipping project memory retrieval.",
        )
        _emit_event(
            event_recorder.emit,
            "failure_memory_retrieval_skipped",
            status="skipped",
            reason="Embedding configuration is incomplete; skipping failure memory retrieval.",
        )
    else:
        try:
            memory_service = ProjectMemoryService(
                runtime_config=runtime_config,
                memory_base_dir=active_memory_base_dir,
            )
            _emit_event(
                event_recorder.emit,
                "memory_retrieval_started",
                scope_key=resolved_memory_scope_key,
                top_k=4,
            )
            retrieval_started_at = time.perf_counter()
            memory_retrieval = memory_service.retrieve(
                memory_scope_key=resolved_memory_scope_key,
                user_query=query,
                data_context=data_context,
                top_k=4,
            )
            _accumulate_duration(
                timing_breakdown,
                "memory_retrieval_duration_ms",
                _elapsed_ms(retrieval_started_at),
            )
            memory_payload["status"] = memory_retrieval.status
            memory_payload["retrieval_status"] = memory_retrieval.status
            memory_payload["retrieval_query"] = memory_retrieval.retrieval_query
            memory_payload["warnings"].extend(memory_retrieval.warnings)
            memory_payload["retrieved_records"] = [record.to_trace_dict() for record in memory_retrieval.records]
            memory_records = memory_retrieval.records
            memory_match_count = memory_retrieval.match_count
            success_memory_context_text = memory_service.format_for_prompt(memory_records)
            if memory_retrieval.status == "retrieved":
                _emit_event(
                    event_recorder.emit,
                    "memory_retrieval_completed",
                    status=memory_retrieval.status,
                    scope_key=resolved_memory_scope_key,
                    match_count=memory_match_count,
                )
            else:
                _emit_event(
                    event_recorder.emit,
                    "memory_retrieval_skipped",
                    status=memory_retrieval.status,
                    reason="No project memory matched this scope.",
                )
        except Exception as exc:
                memory_payload["status"] = "failed"
                memory_payload["retrieval_status"] = "failed"
                memory_payload["warnings"].append(f"Project memory retrieval failed: {exc}")
                _emit_event(
                    event_recorder.emit,
                    "memory_retrieval_skipped",
                    status="failed",
                    reason=f"Project memory retrieval failed: {exc}",
                )
        try:
            failure_memory_service = FailureMemoryService(
                runtime_config=runtime_config,
                memory_base_dir=active_failure_memory_base_dir,
            )
            _emit_event(
                event_recorder.emit,
                "failure_memory_retrieval_started",
                scope_key=resolved_memory_scope_key,
                top_k=4,
            )
            failure_retrieval_started_at = time.perf_counter()
            failure_memory_retrieval = failure_memory_service.retrieve(
                memory_scope_key=resolved_memory_scope_key,
                user_query=query,
                data_context=data_context,
                top_k=4,
            )
            _accumulate_duration(
                timing_breakdown,
                "failure_memory_retrieval_duration_ms",
                _elapsed_ms(failure_retrieval_started_at),
            )
            failure_memory_payload["status"] = failure_memory_retrieval.status
            failure_memory_payload["retrieval_status"] = failure_memory_retrieval.status
            failure_memory_payload["retrieval_query"] = failure_memory_retrieval.retrieval_query
            failure_memory_payload["warnings"].extend(failure_memory_retrieval.warnings)
            failure_memory_payload["retrieved_records"] = [
                record.to_trace_dict() for record in failure_memory_retrieval.records
            ]
            failure_memory_records = failure_memory_retrieval.records
            failure_memory_match_count = failure_memory_retrieval.match_count
            failure_memory_context_text = failure_memory_service.format_for_prompt(failure_memory_records)
            if failure_memory_retrieval.status == "retrieved":
                _emit_event(
                    event_recorder.emit,
                    "failure_memory_retrieval_completed",
                    status=failure_memory_retrieval.status,
                    scope_key=resolved_memory_scope_key,
                    match_count=failure_memory_match_count,
                )
            else:
                _emit_event(
                    event_recorder.emit,
                    "failure_memory_retrieval_skipped",
                    status=failure_memory_retrieval.status,
                    reason="No failure memory matched this scope.",
                )
        except Exception as exc:
            failure_memory_payload["status"] = "failed"
            failure_memory_payload["retrieval_status"] = "failed"
            failure_memory_payload["warnings"].append(f"Failure memory retrieval failed: {exc}")
            _emit_event(
                event_recorder.emit,
                "failure_memory_retrieval_skipped",
                status="failed",
                reason=f"Failure memory retrieval failed: {exc}",
            )
    knowledge_bundle = knowledge_provider.collect(
        data_context=data_context,
        user_query=query,
        success_memory_context=success_memory_context_text,
        failure_memory_context=failure_memory_context_text,
    )
    combined_memory_context_text = _combine_memory_contexts(success_memory_context_text, failure_memory_context_text)
    if not use_rag:
        rag_payload["status"] = "disabled"
        rag_status = "disabled"
        _emit_event(
            event_recorder.emit,
            "knowledge_retrieval_skipped",
            status=rag_status,
            reason="RAG is disabled for this run.",
        )
    elif not runtime_config.embedding_configured and not normalized_knowledge_paths:
        warning_text = "Embedding configuration is incomplete; skipping local RAG retrieval."
        rag_payload["status"] = "skipped"
        rag_status = "skipped"
        rag_payload["warnings"].append(warning_text)
        _emit_event(
            event_recorder.emit,
            "knowledge_retrieval_skipped",
            status=rag_status,
            reason=warning_text,
        )
    else:
        try:
            if not runtime_config.embedding_configured:
                rag_payload["warnings"].append(
                    "Embedding configuration is incomplete; using keyword-only local RAG retrieval."
                )
            rag_service = RagService(
                runtime_config=runtime_config,
                knowledge_base_dir=active_knowledge_base_dir,
            )
            if normalized_knowledge_paths:
                _emit_event(
                    event_recorder.emit,
                    "knowledge_indexing_started",
                    file_count=len(normalized_knowledge_paths),
                    knowledge_base_dir=active_knowledge_base_dir.as_posix(),
                )
                index_started_at = time.perf_counter()
                index_result = rag_service.index_files(normalized_knowledge_paths)
                _accumulate_duration(
                    timing_breakdown,
                    "knowledge_index_duration_ms",
                    _elapsed_ms(index_started_at),
                )
                rag_payload["indexed_documents"] = list(index_result.indexed_documents)
                rag_payload["warnings"].extend(index_result.warnings)
                _emit_event(
                    event_recorder.emit,
                    "knowledge_structured_chunking_completed",
                    chunk_count=index_result.indexed_chunk_count,
                    structured_chunking_enabled=True,
                )
                _emit_event(
                    event_recorder.emit,
                    "knowledge_indexing_completed",
                    status=index_result.status,
                    indexed_count=len(index_result.indexed_documents),
                    warnings=index_result.warnings,
                )
            else:
                _emit_event(
                    event_recorder.emit,
                    "knowledge_indexing_skipped",
                    status="skipped",
                    reason="No new knowledge files were uploaded.",
                )

            query_bundle = rag_service.build_queries(
                data_context=data_context,
                user_query=query,
            )
            rag_payload["retrieval_query"] = query_bundle.retrieval_query
            rag_payload["dense_query"] = query_bundle.dense_query
            rag_payload["keyword_query"] = query_bundle.keyword_query
            if query_bundle.retrieval_query:
                _emit_event(
                    event_recorder.emit,
                    "knowledge_query_built",
                    dense_query=query_bundle.dense_query,
                    keyword_query=query_bundle.keyword_query,
                )
                _emit_event(
                    event_recorder.emit,
                    "knowledge_retrieval_started",
                    query=query_bundle.retrieval_query,
                    top_k=4,
                )
                retrieval_started_at = time.perf_counter()
                retrieval_result = rag_service.retrieve(
                    retrieval_query=query_bundle.retrieval_query,
                    dense_query=query_bundle.dense_query,
                    keyword_query=query_bundle.keyword_query,
                    query_terms=query_bundle.normalized_terms,
                    column_terms=tuple(dict.fromkeys(data_context.columns[:8])),
                    top_k=4,
                )
                _accumulate_duration(
                    timing_breakdown,
                    "knowledge_retrieval_duration_ms",
                    _elapsed_ms(retrieval_started_at),
                )
                rag_payload["warnings"].extend(retrieval_result.warnings)
                rag_payload["dense_candidates"] = [chunk.to_trace_dict() for chunk in retrieval_result.dense_candidates]
                rag_payload["keyword_candidates"] = [chunk.to_trace_dict() for chunk in retrieval_result.keyword_candidates]
                rag_payload["merged_candidates_count"] = len(
                    {
                        *[chunk.chunk_id for chunk in retrieval_result.dense_candidates],
                        *[chunk.chunk_id for chunk in retrieval_result.keyword_candidates],
                    }
                )
                rag_payload["reranked_chunks"] = [chunk.to_trace_dict() for chunk in retrieval_result.reranked_chunks]
                rag_payload["retrieved_chunks"] = [chunk.to_trace_dict() for chunk in retrieval_result.chunks]
                rag_payload["status"] = retrieval_result.status
                rag_payload["retrieval_strategy"] = retrieval_result.retrieval_strategy
                rag_status = retrieval_result.status
                rag_dense_match_count = retrieval_result.dense_match_count
                rag_keyword_match_count = retrieval_result.keyword_match_count
                rag_retrieval_strategy = retrieval_result.retrieval_strategy
                rag_final_chunk_kinds = tuple(
                    dict.fromkeys(str(chunk.chunk_kind or "") or "text_section" for chunk in retrieval_result.reranked_chunks)
                )
                rag_payload["final_chunk_kinds"] = list(rag_final_chunk_kinds)
                _emit_event(
                    event_recorder.emit,
                    "knowledge_dense_retrieval_completed",
                    match_count=rag_dense_match_count,
                )
                _emit_event(
                    event_recorder.emit,
                    "knowledge_keyword_retrieval_completed",
                    match_count=rag_keyword_match_count,
                )
                _emit_event(
                    event_recorder.emit,
                    "knowledge_rerank_completed",
                    match_count=retrieval_result.match_count,
                    retrieval_strategy=rag_retrieval_strategy,
                )
                if retrieval_result.status == "retrieved":
                    rag_match_count = retrieval_result.match_count
                    rag_sources_used = retrieval_result.source_names
                    current_evidence_register = retrieval_result.reranked_chunks or retrieval_result.chunks
                    rag_payload["final_evidence_register"] = [
                        chunk.to_trace_dict() for chunk in current_evidence_register
                    ]
                    knowledge_bundle = knowledge_provider.collect(
                        data_context=data_context,
                        user_query=query,
                        success_memory_context=success_memory_context_text,
                        failure_memory_context=failure_memory_context_text,
                        retrieved_chunks=current_evidence_register,
                    )
                    combined_memory_context_text = _combine_memory_contexts(
                        success_memory_context_text,
                        failure_memory_context_text,
                    )
                    _emit_event(
                        event_recorder.emit,
                        "knowledge_retrieval_completed",
                        status=rag_status,
                        match_count=rag_match_count,
                        sources=list(rag_sources_used),
                    )
                elif retrieval_result.status == "empty":
                    _emit_event(
                        event_recorder.emit,
                        "knowledge_retrieval_skipped",
                        status=rag_status,
                        reason="Knowledge base is empty.",
                    )
                else:
                    _emit_event(
                        event_recorder.emit,
                        "knowledge_retrieval_completed",
                        status=rag_status,
                        match_count=0,
                        sources=[],
                    )
            else:
                rag_payload["status"] = "skipped"
                rag_status = "skipped"
                rag_retrieval_strategy = "hybrid"
                rag_payload["warnings"].append("Retrieval query is empty; local RAG was skipped.")
                _emit_event(
                    event_recorder.emit,
                    "knowledge_retrieval_skipped",
                    status=rag_status,
                    reason="Retrieval query is empty.",
                )
        except Exception as exc:
            warning_text = f"RAG retrieval failed: {exc}"
            rag_payload["status"] = "failed"
            rag_status = "failed"
            rag_payload["warnings"].append(warning_text)
            _emit_event(
                event_recorder.emit,
                "knowledge_retrieval_skipped",
                status=rag_status,
                reason=warning_text,
            )

    tool_registry = build_tool_registry(enable_search=search_enabled)
    _emit_event(
        event_recorder.emit,
        "tool_registry_ready",
        tools=tool_registry.list_tools(),
        search_enabled=search_enabled,
        fast_path_enabled=fast_path_enabled,
        effective_max_steps=effective_max_steps,
    )

    llm = model_registry.build_text_llm(build_llm)
    all_step_traces: list[AgentStepTrace] = []
    analysis_rounds: list[AnalystRoundRecord] = []
    review_history: list[ReviewRecord] = []
    visual_review_history: list[VisualReviewRecord] = []

    raw_result = ""
    report_markdown = ""
    telemetry = ReportTelemetry()
    search_status = "not_used"
    search_notes = "No online knowledge retrieval was triggered."
    tools_used: tuple[str, ...] = ()
    artifact_validation = ArtifactValidationResult(
        workflow_complete=False,
        missing_artifacts=(),
        warnings=(),
        cleaned_data_exists=False,
        report_exists=False,
        trace_exists=False,
    )
    review_status = "skipped" if not review_enabled else "rejected"
    review_critique = ""
    review_rounds_used = 0
    vision_review_status = "skipped"
    vision_review_summary = ""
    visual_attempt_enabled = False
    saved_report_path = final_report_path
    saved_trace_path = trace_path
    analyst_messages: list[dict[str, str]] | None = None
    current_runner: Optional[ScientificReActRunner] = None
    current_execution_audit = StageExecutionAuditResult(status="not_checked")
    current_report_contract = ReportContractCheckResult()

    total_rounds = 1 if not review_enabled else 1 + effective_max_reviews

    for review_round in range(1, total_rounds + 1):
        workflow_tracker.transition(WorkflowState.ANALYZE_ROUND)
        review_figures_dir = _build_review_figures_dir(figures_dir, review_round)
        system_prompt = build_system_prompt(
            run_dir=run_dir.as_posix(),
            cleaned_data_path=cleaned_data_path.as_posix(),
            figures_dir=review_figures_dir.as_posix(),
            logs_dir=logs_dir.as_posix(),
            max_steps=effective_max_steps,
            tool_descriptions=tool_registry.get_tools_description(),
            search_enabled=search_enabled,
            latency_mode=resolved_latency_mode,
            fast_path_enabled=fast_path_enabled,
            symbolic_profile=resolved_symbolic_profile,
        )
        current_runner = ScientificReActRunner(
            name=agent_name,
            llm=llm,
            system_prompt=system_prompt,
            tool_registry=tool_registry,
            max_steps=effective_max_steps,
            fast_path_enabled=fast_path_enabled,
            event_handler=event_recorder.emit,
        )
        run_context_text = _build_run_context_text(run_dir, cleaned_data_path, review_figures_dir, logs_dir)
        if analyst_messages is None:
            analyst_messages = current_runner.build_initial_messages(
                "\n".join(
                    part
                    for part in (
                        query,
                        knowledge_bundle.render_for_prompt(),
                        data_context.context_text,
                        run_context_text,
                    )
                    if part
                )
            )
        else:
            analyst_messages[0] = {"role": "system", "content": system_prompt}

        raw_result, round_traces, analyst_messages = current_runner.run_with_messages(
            analyst_messages,
            analysis_round=review_round,
        )
        _accumulate_duration(
            timing_breakdown,
            "llm_duration_ms",
            sum(trace.llm_duration_ms for trace in round_traces),
        )
        _accumulate_duration(
            timing_breakdown,
            "tool_duration_ms",
            sum(trace.tool_duration_ms for trace in round_traces),
        )
        _accumulate_duration(
            timing_breakdown,
            "tavily_duration_ms",
            sum(trace.tool_duration_ms for trace in round_traces if trace.tool_name == "TavilySearchTool"),
        )
        reindexed_traces = _reindex_step_traces(round_traces, start_index=len(all_step_traces) + 1)
        all_step_traces.extend(reindexed_traces)

        extraction = extract_report_and_telemetry(raw_result)
        report_markdown = extraction.report_markdown
        telemetry = extraction.telemetry
        evidence_coverage = analyze_evidence_coverage(
            report_markdown,
            evidence_register=current_evidence_register,
        )
        rag_citation_count = evidence_coverage.citation_count
        rag_cited_sources = evidence_coverage.cited_sources
        rag_evidence_coverage_status = evidence_coverage.status
        rag_uncited_sections_detected = evidence_coverage.uncited_knowledge_sections_detected
        rag_payload["citation_count"] = rag_citation_count
        rag_payload["cited_evidence_ids"] = list(evidence_coverage.used_evidence_ids)
        rag_payload["cited_sources"] = list(rag_cited_sources)
        rag_payload["evidence_coverage_status"] = rag_evidence_coverage_status
        rag_payload["uncited_sections_detected"] = list(rag_uncited_sections_detected)
        rag_payload["invalid_citation_labels"] = list(evidence_coverage.invalid_citation_labels)

        round_report_path = run_dir / f"review_round_{review_round}_report.md"
        analysis_rounds.append(
            AnalystRoundRecord(
                round_index=review_round,
                report_path=round_report_path,
                step_traces=reindexed_traces,
            )
        )

        round_execution_audit = audit_stage_execution(
            step_traces=reindexed_traces,
            source_data_path=data_context.absolute_path,
            cleaned_data_path=cleaned_data_path,
        )
        current_execution_audit = _select_effective_execution_audit(
            round_execution_audit,
            tuple(analysis_rounds[:-1]),
        )
        current_report_contract = check_report_contract(
            report_markdown,
            task_type=resolved_task_type,
            task_expectations=resolved_task_expectations,
            telemetry=telemetry,
            evidence_coverage=evidence_coverage,
        )
        analysis_rounds[-1] = AnalystRoundRecord(
            round_index=review_round,
            report_path=round_report_path,
            step_traces=reindexed_traces,
            execution_audit=current_execution_audit,
            report_contract_check=current_report_contract,
        )

        _emit_event(
            event_recorder.emit,
            "report_persisting",
            report_path=final_report_path.as_posix(),
            trace_path=trace_path.as_posix(),
            review_round=review_round,
        )
        report_persist_started_at = time.perf_counter()
        saved_report_path = save_markdown_report(report_markdown, final_report_path)
        save_markdown_report(report_markdown, round_report_path)
        _accumulate_duration(timing_breakdown, "report_persist_duration_ms", _elapsed_ms(report_persist_started_at))

        step_traces_tuple = tuple(all_step_traces)
        tools_used = _collect_tools_used(step_traces_tuple, telemetry)
        search_status, search_notes = _determine_search_status(step_traces_tuple, telemetry)

        workflow_tracker.transition(WorkflowState.VALIDATE)
        initial_validation = ArtifactValidationResult(
            workflow_complete=False,
            missing_artifacts=(),
            warnings=(),
            cleaned_data_exists=cleaned_data_path.exists(),
            report_exists=saved_report_path.exists(),
            trace_exists=False,
            stage_contract_status=current_execution_audit.status,
            stage_contract_findings=tuple(finding.message for finding in current_execution_audit.findings),
            stage_contract_passed=current_execution_audit.passed,
        )
        trace_persist_started_at = time.perf_counter()
        saved_trace_path = _save_agent_trace(
            trace_path=trace_path,
            runtime_config=runtime_config,
            data_context=data_context,
            run_dir=run_dir,
            max_steps=max_steps,
            effective_max_steps=effective_max_steps,
            step_traces=step_traces_tuple,
            telemetry=telemetry,
            search_status=search_status,
            search_notes=search_notes,
            tools_used=tools_used,
            artifact_validation=initial_validation,
            analysis_rounds=tuple(analysis_rounds),
            review_history=tuple(review_history),
            visual_review_history=tuple(visual_review_history),
            document_ingestion=document_ingestion,
            review_status=review_status,
            quality_mode=resolved_quality_mode,
            latency_mode=resolved_latency_mode,
            vision_review_mode=resolved_vision_review_mode,
            review_enabled=review_enabled,
            search_enabled=search_enabled,
            fast_path_enabled=fast_path_enabled,
            small_simple_dataset=small_simple_dataset,
            vision_configured=runtime_config.vision_configured,
            timing_breakdown=dict(timing_breakdown),
            run_context=run_context,
            workflow_states=workflow_tracker.snapshot(),
            event_stream=event_recorder.snapshot(),
            rag_payload=rag_payload,
            memory_payload=memory_payload,
            failure_memory_payload=failure_memory_payload,
            execution_audit=current_execution_audit,
            report_contract_check=current_report_contract,
            symbolic_profile=resolved_symbolic_profile,
        )
        _accumulate_duration(timing_breakdown, "trace_persist_duration_ms", _elapsed_ms(trace_persist_started_at))

        artifact_validation = _validate_artifacts(
            cleaned_data_path=cleaned_data_path,
            report_path=saved_report_path,
            trace_path=saved_trace_path,
            telemetry=telemetry,
            execution_audit=current_execution_audit,
        )

        if not review_enabled:
            review_status = "skipped_symbolic_ablation" if resolved_symbolic_profile != "full" else "skipped"
            review_rounds_used = 0
            if resolved_symbolic_profile != "full":
                review_critique = (
                    f"Symbolic profile {resolved_symbolic_profile} runs verifiers posthoc only; "
                    "blocking rejection and revision loop were intentionally disabled."
                )
            else:
                review_critique = (
                    "Review skipped in draft mode."
                    if current_execution_audit.passed and current_report_contract.passed
                    else (
                        "Draft mode skipped reviewer, but stage execution audit did not pass."
                        if not current_execution_audit.passed
                        else "Draft mode skipped reviewer, but the report contract did not pass."
                    )
                )
            break

        if not current_execution_audit.passed:
            reviewer_reply = _build_stage_audit_rejection(current_execution_audit)
            review_log_path = logs_dir / f"review_round_{review_round}_review.json"
            saved_review_log_path = _save_review_log(
                review_log_path=review_log_path,
                review_round=review_round,
                reviewer_reply=reviewer_reply,
                candidate_report_path=saved_report_path,
            )
            review_history.append(
                ReviewRecord(
                    round_index=review_round,
                    decision=reviewer_reply.decision,
                    critique=reviewer_reply.critique,
                    raw_response=reviewer_reply.raw_response,
                    review_log_path=saved_review_log_path,
                    candidate_report_path=saved_report_path,
                    evidence_findings=reviewer_reply.evidence_findings,
                )
            )
            review_rounds_used = review_round
            review_critique = reviewer_reply.critique
            _emit_event(
                event_recorder.emit,
                "review_rejected",
                review_round=review_round,
                critique=reviewer_reply.critique,
            )
            review_status = "rejected"
            if review_round >= total_rounds:
                review_status = "max_reviews_reached"
                _emit_event(
                    event_recorder.emit,
                    "review_max_reached",
                    review_round=review_round,
                    critique=reviewer_reply.critique,
                )
                break

            analyst_messages.append(
                {
                    "role": "user",
                    "content": build_revision_brief(
                        source="stage_execution_audit",
                        blocking_issues=tuple(finding.message for finding in current_execution_audit.findings)
                        or ("Stage execution audit did not pass.",),
                        next_round_figures_dir=(figures_dir / f"review_round_{review_round + 1}").as_posix(),
                    ).to_user_message(),
                }
            )
            continue

            analyst_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"[阶段执行审计未通过]：{reviewer_reply.critique}\n"
                        "你必须先修复执行流程本身：先把原始数据清洗并保存到规范 cleaned_data.csv，"
                        "再在后续新的 Python 步骤中明确重读该文件完成正式分析。"
                        f"下一轮所有新图表必须保存到：{(figures_dir / f'review_round_{review_round + 1}').as_posix()}。"
                    ),
                }
            )
            continue

        if not current_report_contract.passed:
            contract_reply = ParsedReviewerReply(
                decision="Reject",
                critique="Pre-review report contract check failed: " + " | ".join(current_report_contract.blocking_issues),
                raw_response=json.dumps(
                    {
                        "decision": "Reject",
                        "critique": "Pre-review report contract check failed: "
                        + " | ".join(current_report_contract.blocking_issues),
                        "source": "pre_review_contract",
                        "report_contract_check": current_report_contract.to_trace_dict(),
                    },
                    ensure_ascii=False,
                ),
            )
            review_log_path = logs_dir / f"review_round_{review_round}_review.json"
            saved_review_log_path = _save_review_log(
                review_log_path=review_log_path,
                review_round=review_round,
                reviewer_reply=contract_reply,
                candidate_report_path=saved_report_path,
            )
            review_history.append(
                ReviewRecord(
                    round_index=review_round,
                    decision=contract_reply.decision,
                    critique=contract_reply.critique,
                    raw_response=contract_reply.raw_response,
                    review_log_path=saved_review_log_path,
                    candidate_report_path=saved_report_path,
                    evidence_findings=contract_reply.evidence_findings,
                )
            )
            review_rounds_used = review_round
            review_critique = contract_reply.critique
            _emit_event(
                event_recorder.emit,
                "review_rejected",
                review_round=review_round,
                critique=contract_reply.critique,
            )
            review_status = "rejected"
            if review_round >= total_rounds:
                review_status = "max_reviews_reached"
                _emit_event(
                    event_recorder.emit,
                    "review_max_reached",
                    review_round=review_round,
                    critique=contract_reply.critique,
                )
                break

            analyst_messages.append(
                {
                    "role": "user",
                    "content": build_revision_brief(
                        source="pre_review_contract",
                        blocking_issues=current_report_contract.blocking_issues,
                        next_round_figures_dir=(figures_dir / f"review_round_{review_round + 1}").as_posix(),
                    ).to_user_message(),
                }
            )
            continue

        workflow_tracker.transition(WorkflowState.REVIEW)
        visual_attempt_enabled = _should_attempt_vision_review(
            quality_mode=resolved_quality_mode,
            review_enabled=review_enabled,
            vision_review_mode=resolved_vision_review_mode,
        )
        visual_review_log_path = logs_dir / f"review_round_{review_round}_visual_review.json"
        if visual_attempt_enabled:
            _emit_event(
                event_recorder.emit,
                "vision_review_started",
                review_round=review_round,
                report_path=saved_report_path.as_posix(),
            )
            visual_review_result = run_visual_review(
                runtime_config=runtime_config,
                report_markdown=report_markdown,
                telemetry=telemetry,
                run_dir=run_dir,
                review_round=review_round,
                max_images=max(1, int(vision_max_images)),
                max_image_side=max(256, min(int(vision_max_image_side), 2048)),
            )
        else:
            visual_review_result = VisualReviewResult(
                status="skipped",
                decision="Skipped",
                summary="当前质量档位与视觉审稿模式组合未启用视觉审稿。",
            )

        if visual_review_result.duration_ms:
            _accumulate_duration(timing_breakdown, "vision_review_duration_ms", visual_review_result.duration_ms)
        vision_review_status = visual_review_result.status
        vision_review_summary = visual_review_result.summary
        saved_visual_review_log_path = _save_visual_review_log(
            review_log_path=visual_review_log_path,
            review_round=review_round,
            reviewer_reply=visual_review_result,
        )
        visual_review_history.append(
            VisualReviewRecord(
                round_index=review_round,
                status=visual_review_result.status,
                decision=visual_review_result.decision,
                summary=visual_review_result.summary,
                figures_reviewed=visual_review_result.figures_reviewed,
                skipped_figures=visual_review_result.skipped_figures,
                duration_ms=visual_review_result.duration_ms,
                raw_response=visual_review_result.raw_response,
                warning=visual_review_result.warning,
                log_path=saved_visual_review_log_path,
            )
        )
        if visual_review_result.status == "completed":
            _emit_event(
                event_recorder.emit,
                "vision_review_completed",
                review_round=review_round,
                status=visual_review_result.status,
                decision=visual_review_result.decision,
                summary=visual_review_result.summary,
            )
        else:
            _emit_event(
                event_recorder.emit,
                "vision_review_skipped",
                review_round=review_round,
                reason=visual_review_result.summary,
                status=visual_review_result.status,
            )

        reviewer_messages = [
            {
                "role": "system",
                "content": build_reviewer_prompt(
                    resolved_quality_mode,
                    focus_major_issues=(
                        fast_path_enabled
                        and resolved_quality_mode == "standard"
                        and artifact_validation.workflow_complete
                        and not any(trace.tool_status == "error" or trace.parse_error for trace in reindexed_traces)
                    ),
                ),
            },
            {
                "role": "user",
                "content": _build_reviewer_task(
                    data_context=data_context,
                    report_markdown=report_markdown,
                    report_path=saved_report_path,
                    step_traces=reindexed_traces,
                    artifact_validation=artifact_validation,
                    telemetry=telemetry,
                    review_round=review_round,
                    visual_review_summary=_build_visual_review_summary(visual_review_result),
                    evidence_register=current_evidence_register,
                    evidence_coverage=evidence_coverage,
                    memory_context=combined_memory_context_text,
                    execution_audit=current_execution_audit,
                    report_contract_check=current_report_contract,
                    task_type=resolved_task_type,
                    task_expectations=resolved_task_expectations,
                ),
            },
        ]
        _emit_event(
            event_recorder.emit,
            "review_started",
            review_round=review_round,
            report_path=saved_report_path.as_posix(),
        )
        review_started_at = time.perf_counter()
        reviewer_raw_response = str(llm.invoke(reviewer_messages)).strip()
        review_duration_ms = _elapsed_ms(review_started_at)
        _accumulate_duration(timing_breakdown, "review_duration_ms", review_duration_ms)
        _accumulate_duration(timing_breakdown, "llm_duration_ms", review_duration_ms)
        reviewer_reply = _safe_parse_reviewer_reply(reviewer_raw_response)
        review_log_path = logs_dir / f"review_round_{review_round}_review.json"
        saved_review_log_path = _save_review_log(
            review_log_path=review_log_path,
            review_round=review_round,
            reviewer_reply=reviewer_reply,
            candidate_report_path=saved_report_path,
        )
        review_history.append(
            ReviewRecord(
                round_index=review_round,
                decision=reviewer_reply.decision,
                critique=reviewer_reply.critique,
                raw_response=reviewer_reply.raw_response,
                review_log_path=saved_review_log_path,
                candidate_report_path=saved_report_path,
                evidence_findings=reviewer_reply.evidence_findings,
            )
        )
        review_rounds_used = review_round
        review_critique = reviewer_reply.critique

        if reviewer_reply.decision == "Accept":
            review_status = "accepted"
            _emit_event(
                event_recorder.emit,
                "review_accepted",
                review_round=review_round,
                critique=reviewer_reply.critique,
            )
            break

        _emit_event(
            event_recorder.emit,
            "review_rejected",
            review_round=review_round,
            critique=reviewer_reply.critique,
        )

        review_status = "rejected"
        if review_round >= total_rounds:
            review_status = "max_reviews_reached"
            _emit_event(
                event_recorder.emit,
                "review_max_reached",
                review_round=review_round,
                critique=reviewer_reply.critique,
            )
            break

        analyst_messages.append(
            {
                "role": "user",
                "content": build_revision_brief(
                    source="reviewer",
                    blocking_issues=_extract_blocking_issues_from_critique(reviewer_reply.critique),
                    next_round_figures_dir=(figures_dir / f"review_round_{review_round + 1}").as_posix(),
                ).to_user_message(),
            }
        )
        continue

        analyst_messages.append(
            {
                "role": "user",
                "content": (
                    f"[审稿人拒稿意见]：{reviewer_reply.critique}\n"
                    "你必须逐条回应并修复以下全部问题，重新分析并重写报告。"
                    f"下一轮所有新图表必须保存到：{(figures_dir / f'review_round_{review_round + 1}').as_posix()}。"
                    "不要重复原报告中的问题，也不要忽略任何已经指出的主要缺陷。"
                ),
            }
        )

    if report_path is not None:
        save_markdown_report(report_markdown, Path(report_path))

    step_traces_tuple = tuple(all_step_traces)
    tools_used = _collect_tools_used(step_traces_tuple, telemetry)
    search_status, search_notes = _determine_search_status(step_traces_tuple, telemetry)

    timing_snapshot = dict(timing_breakdown)
    timing_snapshot["total_duration_ms"] = _elapsed_ms(run_started_at)

    complete_failure = (
        saved_report_path.exists()
        and saved_trace_path.exists()
        and (
            review_status in {"rejected", "max_reviews_reached"}
            or current_execution_audit.status != "passed"
            or not artifact_validation.workflow_complete
        )
    )

    if (
        resolved_symbolic_profile == "full"
        and review_status == "accepted"
        and artifact_validation.workflow_complete
        and use_memory
        and runtime_config.embedding_configured
    ):
        try:
            _emit_event(
                event_recorder.emit,
                "memory_writeback_started",
                scope_key=resolved_memory_scope_key,
                run_id=run_context.run_id,
            )
            provisional_result = AnalysisRunResult(
                data_context=data_context,
                raw_result=raw_result,
                report_markdown=report_markdown,
                report_path=saved_report_path,
                output_dir=run_dir,
                run_dir=run_dir,
                data_dir=data_dir,
                figures_dir=figures_dir,
                logs_dir=logs_dir,
                trace_path=trace_path,
                cleaned_data_path=cleaned_data_path,
                agent_type=current_runner.__class__.__name__ if current_runner is not None else ScientificReActRunner.__name__,
                step_traces=step_traces_tuple,
                telemetry=telemetry,
                methods_used=telemetry.methods,
                detected_domain=telemetry.domain,
                tools_used=tools_used,
                search_status=search_status,
                search_notes=search_notes,
                workflow_complete=artifact_validation.workflow_complete,
                workflow_warnings=artifact_validation.warnings,
                missing_artifacts=artifact_validation.missing_artifacts,
                quality_mode=resolved_quality_mode,
                review_enabled=review_enabled,
                review_status=review_status,
                review_rounds_used=review_rounds_used,
                review_critique=review_critique,
                review_log_paths=tuple(review.review_log_path for review in review_history),
                symbolic_profile=resolved_symbolic_profile,
                input_kind=document_ingestion.input_kind,
                document_ingestion_status=document_ingestion.status,
                document_ingestion_summary=document_ingestion.summary,
                document_ingestion_duration_ms=timing_snapshot.get("document_ingestion_duration_ms", 0),
                document_ingestion_log_path=document_ingestion.log_path,
                candidate_table_count=document_ingestion.candidate_table_count,
                selected_table_id=document_ingestion.selected_table_id,
                selected_table_shape=document_ingestion.selected_table_shape,
                pdf_multi_table_mode=document_ingestion.pdf_multi_table_mode,
                latency_mode=resolved_latency_mode,
                vision_review_mode=resolved_vision_review_mode,
                vision_review_enabled=visual_attempt_enabled if review_enabled else False,
                vision_review_status=vision_review_status,
                vision_review_summary=vision_review_summary,
                vision_review_duration_ms=timing_snapshot.get("vision_review_duration_ms", 0),
                vision_review_log_paths=tuple(review.log_path for review in visual_review_history),
                rag_enabled=use_rag,
                rag_status=rag_status,
                rag_match_count=rag_match_count,
                rag_sources_used=rag_sources_used,
                rag_dense_match_count=rag_dense_match_count,
                rag_keyword_match_count=rag_keyword_match_count,
                rag_retrieval_strategy=rag_retrieval_strategy,
                rag_table_candidate_count=rag_table_candidate_count,
                rag_final_chunk_kinds=rag_final_chunk_kinds,
                rag_selected_table_hit=rag_selected_table_hit,
                rag_citation_count=rag_citation_count,
                rag_cited_sources=rag_cited_sources,
                rag_evidence_coverage_status=rag_evidence_coverage_status,
                rag_uncited_sections_detected=rag_uncited_sections_detected,
                memory_enabled=use_memory,
                memory_scope_key=resolved_memory_scope_key,
                memory_match_count=memory_match_count,
                memory_writeback_status=memory_writeback_status,
                memory_written_count=memory_written_count,
                failure_memory_enabled=use_memory,
                failure_memory_match_count=failure_memory_match_count,
                failure_memory_writeback_status=failure_memory_writeback_status,
                failure_memory_written_count=failure_memory_written_count,
                total_duration_ms=timing_snapshot.get("total_duration_ms", 0),
                llm_duration_ms=timing_snapshot.get("llm_duration_ms", 0),
                tool_duration_ms=timing_snapshot.get("tool_duration_ms", 0),
                review_duration_ms=timing_snapshot.get("review_duration_ms", 0),
                timing_breakdown=timing_snapshot,
                execution_audit_status=current_execution_audit.status,
                execution_audit_passed=current_execution_audit.passed,
                execution_audit_findings=tuple(finding.message for finding in current_execution_audit.findings),
                report_contract_passed=current_report_contract.passed,
                report_contract_blocking_issues=current_report_contract.blocking_issues,
                report_contract_issue_types=current_report_contract.issue_types,
            )
            extraction_result = extract_memory_records(
                result=provisional_result,
                review_history=tuple(review_history),
                memory_scope_key=resolved_memory_scope_key,
                llm=llm,
            )
            memory_payload["warnings"].extend(extraction_result.warnings)
            memory_service = ProjectMemoryService(
                runtime_config=runtime_config,
                memory_base_dir=active_memory_base_dir,
            )
            write_started_at = time.perf_counter()
            memory_write = memory_service.write_records(
                records=extraction_result.records,
                run_id=run_context.run_id,
            )
            _accumulate_duration(
                timing_breakdown,
                "memory_writeback_duration_ms",
                _elapsed_ms(write_started_at),
            )
            memory_writeback_status = memory_write.status
            memory_written_count = memory_write.written_count
            memory_payload["writeback_status"] = memory_write.status
            memory_payload["written_record_ids"] = [record.memory_id for record in memory_write.written_records]
            memory_payload["llm_distilled"] = extraction_result.llm_distilled
            memory_payload["warnings"].extend(memory_write.warnings)
            _emit_event(
                event_recorder.emit,
                "memory_writeback_completed" if memory_write.status in {"written", "already_written"} else "memory_writeback_skipped",
                status=memory_write.status,
                scope_key=resolved_memory_scope_key,
                written_count=memory_written_count,
            )
        except Exception as exc:
            memory_writeback_status = "failed"
            memory_payload["writeback_status"] = "failed"
            memory_payload["warnings"].append(f"Project memory writeback failed: {exc}")
            _emit_event(
                event_recorder.emit,
                "memory_writeback_skipped",
                status="failed",
                reason=f"Project memory writeback failed: {exc}",
            )
    else:
        if not use_memory:
            memory_writeback_status = "disabled"
        elif review_status != "accepted":
            memory_writeback_status = "not_accepted"
        elif not artifact_validation.workflow_complete:
            memory_writeback_status = "workflow_incomplete"
        elif not runtime_config.embedding_configured:
            memory_writeback_status = "skipped"
        memory_payload["writeback_status"] = memory_writeback_status
        _emit_event(
            event_recorder.emit,
            "memory_writeback_skipped",
            status=memory_writeback_status,
            reason="Project memory writeback not triggered for this run.",
        )

    if complete_failure and resolved_symbolic_profile == "full" and use_memory and runtime_config.embedding_configured:
        try:
            _emit_event(
                event_recorder.emit,
                "failure_memory_writeback_started",
                scope_key=resolved_memory_scope_key,
                run_id=run_context.run_id,
            )
            provisional_failure_result = AnalysisRunResult(
                data_context=data_context,
                raw_result=raw_result,
                report_markdown=report_markdown,
                report_path=saved_report_path,
                output_dir=run_dir,
                run_dir=run_dir,
                data_dir=data_dir,
                figures_dir=figures_dir,
                logs_dir=logs_dir,
                trace_path=trace_path,
                cleaned_data_path=cleaned_data_path,
                agent_type=current_runner.__class__.__name__ if current_runner is not None else ScientificReActRunner.__name__,
                step_traces=step_traces_tuple,
                telemetry=telemetry,
                methods_used=telemetry.methods,
                detected_domain=telemetry.domain,
                tools_used=tools_used,
                search_status=search_status,
                search_notes=search_notes,
                workflow_complete=artifact_validation.workflow_complete,
                workflow_warnings=artifact_validation.warnings,
                missing_artifacts=artifact_validation.missing_artifacts,
                quality_mode=resolved_quality_mode,
                review_enabled=review_enabled,
                review_status=review_status,
                review_rounds_used=review_rounds_used,
                review_critique=review_critique,
                review_log_paths=tuple(review.review_log_path for review in review_history),
                symbolic_profile=resolved_symbolic_profile,
                input_kind=document_ingestion.input_kind,
                document_ingestion_status=document_ingestion.status,
                document_ingestion_summary=document_ingestion.summary,
                document_ingestion_duration_ms=timing_snapshot.get("document_ingestion_duration_ms", 0),
                document_ingestion_log_path=document_ingestion.log_path,
                candidate_table_count=document_ingestion.candidate_table_count,
                selected_table_id=document_ingestion.selected_table_id,
                selected_table_shape=document_ingestion.selected_table_shape,
                pdf_multi_table_mode=document_ingestion.pdf_multi_table_mode,
                latency_mode=resolved_latency_mode,
                vision_review_mode=resolved_vision_review_mode,
                vision_review_enabled=visual_attempt_enabled if review_enabled else False,
                vision_review_status=vision_review_status,
                vision_review_summary=vision_review_summary,
                vision_review_duration_ms=timing_snapshot.get("vision_review_duration_ms", 0),
                vision_review_log_paths=tuple(review.log_path for review in visual_review_history),
                rag_enabled=use_rag,
                rag_status=rag_status,
                rag_match_count=rag_match_count,
                rag_sources_used=rag_sources_used,
                rag_dense_match_count=rag_dense_match_count,
                rag_keyword_match_count=rag_keyword_match_count,
                rag_retrieval_strategy=rag_retrieval_strategy,
                rag_table_candidate_count=rag_table_candidate_count,
                rag_final_chunk_kinds=rag_final_chunk_kinds,
                rag_selected_table_hit=rag_selected_table_hit,
                rag_citation_count=rag_citation_count,
                rag_cited_sources=rag_cited_sources,
                rag_evidence_coverage_status=rag_evidence_coverage_status,
                rag_uncited_sections_detected=rag_uncited_sections_detected,
                memory_enabled=use_memory,
                memory_scope_key=resolved_memory_scope_key,
                memory_match_count=memory_match_count,
                memory_writeback_status=memory_writeback_status,
                memory_written_count=memory_written_count,
                failure_memory_enabled=use_memory,
                failure_memory_match_count=failure_memory_match_count,
                failure_memory_writeback_status=failure_memory_writeback_status,
                failure_memory_written_count=failure_memory_written_count,
                total_duration_ms=timing_snapshot.get("total_duration_ms", 0),
                llm_duration_ms=timing_snapshot.get("llm_duration_ms", 0),
                tool_duration_ms=timing_snapshot.get("tool_duration_ms", 0),
                review_duration_ms=timing_snapshot.get("review_duration_ms", 0),
                timing_breakdown=timing_snapshot,
                execution_audit_status=current_execution_audit.status,
                execution_audit_passed=current_execution_audit.passed,
                execution_audit_findings=tuple(finding.message for finding in current_execution_audit.findings),
                report_contract_passed=current_report_contract.passed,
                report_contract_blocking_issues=current_report_contract.blocking_issues,
                report_contract_issue_types=current_report_contract.issue_types,
            )
            failure_extraction_result = extract_failure_memory_records(
                result=provisional_failure_result,
                review_history=tuple(review_history),
                memory_scope_key=resolved_memory_scope_key,
            )
            failure_memory_payload["warnings"].extend(failure_extraction_result.warnings)
            failure_memory_service = FailureMemoryService(
                runtime_config=runtime_config,
                memory_base_dir=active_failure_memory_base_dir,
            )
            failure_write_started_at = time.perf_counter()
            failure_memory_write = failure_memory_service.write_records(
                records=failure_extraction_result.records,
                run_id=run_context.run_id,
            )
            _accumulate_duration(
                timing_breakdown,
                "failure_memory_writeback_duration_ms",
                _elapsed_ms(failure_write_started_at),
            )
            failure_memory_writeback_status = failure_memory_write.status
            failure_memory_written_count = failure_memory_write.written_count
            failure_memory_payload["writeback_status"] = failure_memory_write.status
            failure_memory_payload["written_record_ids"] = [
                record.memory_id for record in failure_memory_write.written_records
            ]
            failure_memory_payload["warnings"].extend(failure_memory_write.warnings)
            _emit_event(
                event_recorder.emit,
                "failure_memory_writeback_completed"
                if failure_memory_write.status in {"written", "already_written"}
                else "failure_memory_writeback_skipped",
                status=failure_memory_write.status,
                scope_key=resolved_memory_scope_key,
                written_count=failure_memory_written_count,
            )
        except Exception as exc:
            failure_memory_writeback_status = "failed"
            failure_memory_payload["writeback_status"] = "failed"
            failure_memory_payload["warnings"].append(f"Failure memory writeback failed: {exc}")
            _emit_event(
                event_recorder.emit,
                "failure_memory_writeback_skipped",
                status="failed",
                reason=f"Failure memory writeback failed: {exc}",
            )
    else:
        if not use_memory:
            failure_memory_writeback_status = "disabled"
        elif complete_failure and resolved_symbolic_profile != "full":
            failure_memory_writeback_status = "symbolic_ablation_skipped"
        elif not complete_failure:
            failure_memory_writeback_status = "not_applicable"
        elif not runtime_config.embedding_configured:
            failure_memory_writeback_status = "skipped"
        failure_memory_payload["writeback_status"] = failure_memory_writeback_status
        _emit_event(
            event_recorder.emit,
            "failure_memory_writeback_skipped",
            status=failure_memory_writeback_status,
            reason="Failure memory writeback not triggered for this run.",
        )

    final_trace_persist_started_at = time.perf_counter()
    _save_agent_trace(
        trace_path=trace_path,
        runtime_config=runtime_config,
        data_context=data_context,
        run_dir=run_dir,
        max_steps=max_steps,
        effective_max_steps=effective_max_steps,
        step_traces=step_traces_tuple,
        telemetry=telemetry,
        search_status=search_status,
        search_notes=search_notes,
        tools_used=tools_used,
        artifact_validation=artifact_validation,
        analysis_rounds=tuple(analysis_rounds),
        review_history=tuple(review_history),
        visual_review_history=tuple(visual_review_history),
        document_ingestion=document_ingestion,
        review_status=review_status,
        quality_mode=resolved_quality_mode,
        latency_mode=resolved_latency_mode,
        vision_review_mode=resolved_vision_review_mode,
        review_enabled=review_enabled,
        search_enabled=search_enabled,
        fast_path_enabled=fast_path_enabled,
        small_simple_dataset=small_simple_dataset,
        vision_configured=runtime_config.vision_configured,
        timing_breakdown=timing_snapshot,
        run_context=run_context,
        workflow_states=workflow_tracker.snapshot(),
        event_stream=event_recorder.snapshot(),
        rag_payload=rag_payload,
        memory_payload=memory_payload,
        failure_memory_payload=failure_memory_payload,
        execution_audit=current_execution_audit,
        report_contract_check=current_report_contract,
        symbolic_profile=resolved_symbolic_profile,
    )
    _accumulate_duration(
        timing_breakdown,
        "trace_persist_duration_ms",
        _elapsed_ms(final_trace_persist_started_at),
    )
    final_timing_breakdown = dict(timing_breakdown)
    final_timing_breakdown["total_duration_ms"] = _elapsed_ms(run_started_at)

    workflow_tracker.transition(WorkflowState.FINALIZE)
    _emit_event(
        event_recorder.emit,
        "report_saved",
        report_path=saved_report_path.as_posix(),
        trace_path=saved_trace_path.as_posix(),
        tools_used=tools_used,
        search_status=search_status,
        telemetry_valid=telemetry.valid,
    )
    _emit_event(
        event_recorder.emit,
        "artifact_validation_completed",
        workflow_complete=artifact_validation.workflow_complete,
        missing_artifacts=artifact_validation.missing_artifacts,
        warnings=artifact_validation.warnings,
    )

    final_result = AnalysisRunResult(
        data_context=data_context,
        raw_result=raw_result,
        report_markdown=report_markdown,
        report_path=saved_report_path,
        output_dir=run_dir,
        run_dir=run_dir,
        data_dir=data_dir,
        figures_dir=figures_dir,
        logs_dir=logs_dir,
        trace_path=saved_trace_path,
        cleaned_data_path=cleaned_data_path,
        agent_type=current_runner.__class__.__name__ if current_runner is not None else ScientificReActRunner.__name__,
        step_traces=step_traces_tuple,
        telemetry=telemetry,
        methods_used=telemetry.methods,
        detected_domain=telemetry.domain,
        tools_used=tools_used,
        search_status=search_status,
        search_notes=search_notes,
        workflow_complete=artifact_validation.workflow_complete,
        workflow_warnings=artifact_validation.warnings,
        missing_artifacts=artifact_validation.missing_artifacts,
        quality_mode=resolved_quality_mode,
        review_enabled=review_enabled,
        review_status=review_status,
        review_rounds_used=review_rounds_used,
        review_critique=review_critique,
        review_log_paths=tuple(review.review_log_path for review in review_history),
        symbolic_profile=resolved_symbolic_profile,
        input_kind=document_ingestion.input_kind,
        document_ingestion_status=document_ingestion.status,
        document_ingestion_summary=document_ingestion.summary,
        document_ingestion_duration_ms=final_timing_breakdown.get("document_ingestion_duration_ms", 0),
        document_ingestion_log_path=document_ingestion.log_path,
        candidate_table_count=document_ingestion.candidate_table_count,
        selected_table_id=document_ingestion.selected_table_id,
        selected_table_shape=document_ingestion.selected_table_shape,
        pdf_multi_table_mode=document_ingestion.pdf_multi_table_mode,
        latency_mode=resolved_latency_mode,
        vision_review_mode=resolved_vision_review_mode,
        vision_review_enabled=visual_attempt_enabled if review_enabled else False,
        vision_review_status=vision_review_status,
        vision_review_summary=vision_review_summary,
        vision_review_duration_ms=final_timing_breakdown.get("vision_review_duration_ms", 0),
        vision_review_log_paths=tuple(review.log_path for review in visual_review_history),
        rag_enabled=use_rag,
        rag_status=rag_status,
        rag_match_count=rag_match_count,
        rag_sources_used=rag_sources_used,
        rag_dense_match_count=rag_dense_match_count,
        rag_keyword_match_count=rag_keyword_match_count,
        rag_retrieval_strategy=rag_retrieval_strategy,
        rag_table_candidate_count=rag_table_candidate_count,
        rag_final_chunk_kinds=rag_final_chunk_kinds,
        rag_selected_table_hit=rag_selected_table_hit,
        rag_citation_count=rag_citation_count,
        rag_cited_sources=rag_cited_sources,
        rag_evidence_coverage_status=rag_evidence_coverage_status,
        rag_uncited_sections_detected=rag_uncited_sections_detected,
        memory_enabled=use_memory,
        memory_scope_key=resolved_memory_scope_key,
        memory_match_count=memory_match_count,
        memory_writeback_status=memory_writeback_status,
        memory_written_count=memory_written_count,
        failure_memory_enabled=use_memory,
        failure_memory_match_count=failure_memory_match_count,
        failure_memory_writeback_status=failure_memory_writeback_status,
        failure_memory_written_count=failure_memory_written_count,
        total_duration_ms=final_timing_breakdown.get("total_duration_ms", 0),
        llm_duration_ms=final_timing_breakdown.get("llm_duration_ms", 0),
        tool_duration_ms=final_timing_breakdown.get("tool_duration_ms", 0),
        review_duration_ms=final_timing_breakdown.get("review_duration_ms", 0),
        timing_breakdown=final_timing_breakdown,
        execution_audit_status=current_execution_audit.status,
        execution_audit_passed=current_execution_audit.passed,
        execution_audit_findings=tuple(finding.message for finding in current_execution_audit.findings),
        report_contract_passed=current_report_contract.passed,
        report_contract_blocking_issues=current_report_contract.blocking_issues,
        report_contract_issue_types=current_report_contract.issue_types,
    )
    _save_run_summary_service(
        summary_path=run_dir / "run_summary.json",
        payload=build_run_summary_payload(final_result),
    )
    return final_result
