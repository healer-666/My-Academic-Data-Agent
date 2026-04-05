"""Typed workflow event protocol."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict

from .runtime_models import WorkflowState


class EventType(str, Enum):
    CONFIG_LOADING = "config_loading"
    CONFIG_LOADED = "config_loaded"
    RUN_DIRECTORY_CREATED = "run_directory_created"
    DOCUMENT_INGESTION_STARTED = "document_ingestion_started"
    DOCUMENT_INGESTION_COMPLETED = "document_ingestion_completed"
    DOCUMENT_INGESTION_SKIPPED = "document_ingestion_skipped"
    DATA_CONTEXT_LOADING = "data_context_loading"
    DATA_CONTEXT_READY = "data_context_ready"
    KNOWLEDGE_INDEXING_STARTED = "knowledge_indexing_started"
    KNOWLEDGE_INDEXING_COMPLETED = "knowledge_indexing_completed"
    KNOWLEDGE_INDEXING_SKIPPED = "knowledge_indexing_skipped"
    KNOWLEDGE_STRUCTURED_CHUNKING_COMPLETED = "knowledge_structured_chunking_completed"
    KNOWLEDGE_TABLE_CANDIDATES_PREPARED = "knowledge_table_candidates_prepared"
    KNOWLEDGE_QUERY_BUILT = "knowledge_query_built"
    KNOWLEDGE_DENSE_RETRIEVAL_COMPLETED = "knowledge_dense_retrieval_completed"
    KNOWLEDGE_KEYWORD_RETRIEVAL_COMPLETED = "knowledge_keyword_retrieval_completed"
    KNOWLEDGE_RERANK_COMPLETED = "knowledge_rerank_completed"
    KNOWLEDGE_RETRIEVAL_STARTED = "knowledge_retrieval_started"
    KNOWLEDGE_RETRIEVAL_COMPLETED = "knowledge_retrieval_completed"
    KNOWLEDGE_RETRIEVAL_SKIPPED = "knowledge_retrieval_skipped"
    MEMORY_RETRIEVAL_STARTED = "memory_retrieval_started"
    MEMORY_RETRIEVAL_COMPLETED = "memory_retrieval_completed"
    MEMORY_RETRIEVAL_SKIPPED = "memory_retrieval_skipped"
    MEMORY_WRITEBACK_STARTED = "memory_writeback_started"
    MEMORY_WRITEBACK_COMPLETED = "memory_writeback_completed"
    MEMORY_WRITEBACK_SKIPPED = "memory_writeback_skipped"
    TOOL_REGISTRY_READY = "tool_registry_ready"
    ANALYSIS_STARTED = "analysis_started"
    STEP_STARTED = "step_started"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    STEP_PARSE_ERROR = "step_parse_error"
    REPORT_PERSISTING = "report_persisting"
    REPORT_SAVED = "report_saved"
    ARTIFACT_VALIDATION_COMPLETED = "artifact_validation_completed"
    ANALYSIS_FINISHED = "analysis_finished"
    ANALYSIS_MAX_STEPS = "analysis_max_steps"
    VISION_REVIEW_STARTED = "vision_review_started"
    VISION_REVIEW_COMPLETED = "vision_review_completed"
    VISION_REVIEW_SKIPPED = "vision_review_skipped"
    REVIEW_STARTED = "review_started"
    REVIEW_REJECTED = "review_rejected"
    REVIEW_ACCEPTED = "review_accepted"
    REVIEW_MAX_REACHED = "review_max_reached"
    WORKFLOW_STATE_CHANGED = "workflow_state_changed"


@dataclass(frozen=True)
class AgentEvent:
    event_type: EventType
    payload: dict[str, Any]
    workflow_state: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "workflow_state": self.workflow_state,
            "payload": dict(self.payload),
        }


EventHandler = Callable[[str, Dict[str, Any]], None]


def normalize_event_type(event_type: EventType | str) -> EventType:
    return event_type if isinstance(event_type, EventType) else EventType(str(event_type))


def emit_event(
    event_handler: EventHandler | None,
    event_type: EventType | str,
    *,
    workflow_state: WorkflowState | str | None = None,
    **payload: Any,
) -> AgentEvent:
    normalized = normalize_event_type(event_type)
    state_value = ""
    if workflow_state is not None:
        state_value = workflow_state.value if isinstance(workflow_state, WorkflowState) else str(workflow_state)
        payload.setdefault("workflow_state", state_value)
    event = AgentEvent(event_type=normalized, payload=dict(payload), workflow_state=state_value)
    if event_handler is not None:
        event_handler(normalized.value, dict(payload))
    return event


class EventRecorder:
    def __init__(self, downstream: EventHandler | None = None) -> None:
        self.downstream = downstream
        self._events: list[AgentEvent] = []

    def emit(
        self,
        event_type: EventType | str,
        *,
        workflow_state: WorkflowState | str | None = None,
        **payload: Any,
    ) -> AgentEvent:
        event = emit_event(self.downstream, event_type, workflow_state=workflow_state, **payload)
        self._events.append(event)
        return event

    def snapshot(self) -> tuple[AgentEvent, ...]:
        return tuple(self._events)
