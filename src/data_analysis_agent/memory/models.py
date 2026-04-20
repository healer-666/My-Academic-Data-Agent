"""Project-level memory models."""

from __future__ import annotations

from dataclasses import dataclass
import json


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    memory_scope_key: str
    memory_type: str
    run_id: str
    source_report_path: str
    detected_domain: str
    quality_mode: str
    created_at: str
    source_count: int
    review_status: str
    text: str
    source_names: tuple[str, ...] = ()
    usage_mode: str = "positive"

    def to_metadata(self) -> dict[str, str | int]:
        metadata: dict[str, str | int] = {
            "memory_id": self.memory_id,
            "memory_scope_key": self.memory_scope_key,
            "memory_type": self.memory_type,
            "run_id": self.run_id,
            "source_report_path": self.source_report_path,
            "detected_domain": self.detected_domain,
            "quality_mode": self.quality_mode,
            "created_at": self.created_at,
            "source_count": int(self.source_count),
            "review_status": self.review_status,
            "usage_mode": self.usage_mode,
        }
        if self.source_names:
            metadata["source_names"] = json.dumps(list(self.source_names), ensure_ascii=False)
        return metadata

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "memory_id": self.memory_id,
            "memory_scope_key": self.memory_scope_key,
            "memory_type": self.memory_type,
            "run_id": self.run_id,
            "source_report_path": self.source_report_path,
            "detected_domain": self.detected_domain,
            "quality_mode": self.quality_mode,
            "created_at": self.created_at,
            "source_count": self.source_count,
            "review_status": self.review_status,
            "source_names": list(self.source_names),
            "text_excerpt": self.text[:320],
            "usage_mode": self.usage_mode,
        }


@dataclass(frozen=True)
class MemoryWriteResult:
    status: str
    written_records: tuple[MemoryRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    llm_distilled: bool = False

    @property
    def written_count(self) -> int:
        return len(self.written_records)


@dataclass(frozen=True)
class MemoryRetrievalResult:
    status: str
    memory_scope_key: str = ""
    retrieval_query: str = ""
    records: tuple[MemoryRecord, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def match_count(self) -> int:
        return len(self.records)


@dataclass(frozen=True)
class FailureMemoryRecord:
    memory_id: str
    memory_scope_key: str
    failure_type: str
    run_id: str
    source_report_path: str
    source_trace_path: str
    detected_domain: str
    quality_mode: str
    created_at: str
    review_status: str
    workflow_complete: bool
    execution_audit_status: str
    trigger_stage: str
    text: str
    avoidance_rule: str
    source_names: tuple[str, ...] = ()
    usage_mode: str = "negative"

    def to_metadata(self) -> dict[str, str | int | bool]:
        metadata: dict[str, str | int | bool] = {
            "memory_id": self.memory_id,
            "memory_scope_key": self.memory_scope_key,
            "failure_type": self.failure_type,
            "run_id": self.run_id,
            "source_report_path": self.source_report_path,
            "source_trace_path": self.source_trace_path,
            "detected_domain": self.detected_domain,
            "quality_mode": self.quality_mode,
            "created_at": self.created_at,
            "review_status": self.review_status,
            "workflow_complete": self.workflow_complete,
            "execution_audit_status": self.execution_audit_status,
            "trigger_stage": self.trigger_stage,
            "avoidance_rule": self.avoidance_rule,
            "usage_mode": self.usage_mode,
        }
        if self.source_names:
            metadata["source_names"] = json.dumps(list(self.source_names), ensure_ascii=False)
        return metadata

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "memory_id": self.memory_id,
            "memory_scope_key": self.memory_scope_key,
            "failure_type": self.failure_type,
            "run_id": self.run_id,
            "source_report_path": self.source_report_path,
            "source_trace_path": self.source_trace_path,
            "detected_domain": self.detected_domain,
            "quality_mode": self.quality_mode,
            "created_at": self.created_at,
            "review_status": self.review_status,
            "workflow_complete": self.workflow_complete,
            "execution_audit_status": self.execution_audit_status,
            "trigger_stage": self.trigger_stage,
            "avoidance_rule": self.avoidance_rule,
            "source_names": list(self.source_names),
            "text_excerpt": self.text[:320],
            "usage_mode": self.usage_mode,
        }


@dataclass(frozen=True)
class FailureMemoryWriteResult:
    status: str
    written_records: tuple[FailureMemoryRecord, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def written_count(self) -> int:
        return len(self.written_records)


@dataclass(frozen=True)
class FailureMemoryRetrievalResult:
    status: str
    memory_scope_key: str = ""
    retrieval_query: str = ""
    records: tuple[FailureMemoryRecord, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def match_count(self) -> int:
        return len(self.records)
