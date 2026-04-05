"""Project-scoped memory retrieval and writeback service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..config import RuntimeConfig
from ..rag.embeddings import OpenAIEmbeddingClient
from .models import MemoryRecord, MemoryRetrievalResult, MemoryWriteResult


class ProjectMemoryService:
    COLLECTION_NAME = "academic_data_agent_project_memory"

    def __init__(
        self,
        *,
        runtime_config: RuntimeConfig,
        memory_base_dir: str | Path | None = None,
    ) -> None:
        self.runtime_config = runtime_config
        self.memory_base_dir = Path(memory_base_dir or Path("memory") / "project_memory").resolve()
        self.chroma_dir = self.memory_base_dir / "chroma"
        self.embedding_client = OpenAIEmbeddingClient(
            model_id=runtime_config.embedding_model_id or "",
            api_key=runtime_config.embedding_api_key or "",
            base_url=runtime_config.embedding_base_url or "",
            timeout=runtime_config.embedding_timeout,
        )

    def retrieve(
        self,
        *,
        memory_scope_key: str,
        user_query: str,
        data_context,
        top_k: int = 4,
    ) -> MemoryRetrievalResult:
        normalized_scope_key = str(memory_scope_key or "").strip()
        if not normalized_scope_key:
            return MemoryRetrievalResult(status="skipped")

        query = self.build_query(user_query=user_query, data_context=data_context)
        if not query:
            return MemoryRetrievalResult(status="skipped", memory_scope_key=normalized_scope_key)

        collection = self._get_collection()
        try:
            existing = collection.get(where={"memory_scope_key": normalized_scope_key}, include=[])
            ids = existing.get("ids", []) if isinstance(existing, dict) else []
            if not ids:
                return MemoryRetrievalResult(
                    status="empty",
                    memory_scope_key=normalized_scope_key,
                    retrieval_query=query,
                )
            embeddings = self.embedding_client.embed_texts([query])
            query_embedding = embeddings[0] if embeddings else []
            if not query_embedding:
                return MemoryRetrievalResult(
                    status="skipped",
                    memory_scope_key=normalized_scope_key,
                    retrieval_query=query,
                )
            payload = collection.query(
                query_embeddings=[query_embedding],
                n_results=max(1, int(top_k)),
                where={"memory_scope_key": normalized_scope_key},
                include=["documents", "metadatas"],
            )
        except Exception as exc:
            return MemoryRetrievalResult(
                status="failed",
                memory_scope_key=normalized_scope_key,
                retrieval_query=query,
                warnings=(str(exc),),
            )

        records = _parse_retrieved_records(payload)
        return MemoryRetrievalResult(
            status="retrieved" if records else "empty",
            memory_scope_key=normalized_scope_key,
            retrieval_query=query,
            records=records,
        )

    def write_records(
        self,
        *,
        records: Iterable[MemoryRecord],
        run_id: str,
    ) -> MemoryWriteResult:
        record_list = tuple(records)
        if not record_list:
            return MemoryWriteResult(status="empty")
        collection = self._get_collection()
        try:
            existing = collection.get(where={"run_id": str(run_id)}, include=[])
            ids = existing.get("ids", []) if isinstance(existing, dict) else []
            if ids:
                return MemoryWriteResult(status="already_written")
            embeddings = self.embedding_client.embed_texts(record.text for record in record_list)
            if len(embeddings) != len(record_list):
                raise ValueError("Memory embedding response count mismatch.")
            collection.upsert(
                ids=[record.memory_id for record in record_list],
                documents=[record.text for record in record_list],
                metadatas=[record.to_metadata() for record in record_list],
                embeddings=embeddings,
            )
        except Exception as exc:
            return MemoryWriteResult(status="failed", warnings=(str(exc),))
        return MemoryWriteResult(status="written", written_records=record_list)

    def format_for_prompt(self, records: Iterable[MemoryRecord], *, max_chars: int = 2200) -> str:
        lines: list[str] = []
        total_chars = 0
        for record in records:
            source_hint = f"run={record.run_id}"
            line = f"[{record.memory_type} | {source_hint}] {record.text}"
            remaining = max_chars - total_chars
            if remaining <= 0:
                break
            if len(line) > remaining:
                line = line[:remaining].rstrip() + " ..."
            lines.append(line)
            total_chars += len(line)
            if total_chars >= max_chars:
                break
        return "\n".join(lines).strip()

    def build_query(self, *, user_query: str, data_context) -> str:
        parts = [
            str(user_query or "").strip(),
            ", ".join(getattr(data_context, "columns", [])[:8]),
            ", ".join(getattr(data_context, "selected_table_headers", ())[:6]),
            ", ".join(getattr(data_context, "selected_table_numeric_columns", ())[:6]),
            str(getattr(data_context, "background_literature_context", "") or "")[:220],
            str(getattr(data_context, "selected_table_id", "") or "").strip(),
        ]
        normalized = " | ".join(part for part in parts if part)
        return " ".join(normalized.split()).strip()

    def _get_collection(self):
        try:
            import chromadb
        except Exception as exc:
            raise RuntimeError(f"chromadb is unavailable: {exc}") from exc
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self.chroma_dir))
        return client.get_or_create_collection(name=self.COLLECTION_NAME)


def _parse_retrieved_records(payload: dict[str, object]) -> tuple[MemoryRecord, ...]:
    documents = payload.get("documents", [[]]) if isinstance(payload, dict) else [[]]
    metadatas = payload.get("metadatas", [[]]) if isinstance(payload, dict) else [[]]
    records: list[MemoryRecord] = []
    for index, document in enumerate(documents[0] if documents else []):
        metadata = (metadatas[0] if metadatas else [])[index] if metadatas else {}
        if not isinstance(metadata, dict):
            metadata = {}
        records.append(
            MemoryRecord(
                memory_id=str(metadata.get("memory_id", "") or ""),
                memory_scope_key=str(metadata.get("memory_scope_key", "") or ""),
                memory_type=str(metadata.get("memory_type", "") or "analysis_summary"),
                run_id=str(metadata.get("run_id", "") or ""),
                source_report_path=str(metadata.get("source_report_path", "") or ""),
                detected_domain=str(metadata.get("detected_domain", "") or "unknown"),
                quality_mode=str(metadata.get("quality_mode", "") or "standard"),
                created_at=str(metadata.get("created_at", "") or ""),
                source_count=_coerce_int(metadata.get("source_count")),
                review_status=str(metadata.get("review_status", "") or "accepted"),
                text=str(document or ""),
                source_names=_coerce_str_tuple(metadata.get("source_names")),
            )
        )
    return tuple(records)


def _coerce_int(value: object) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _coerce_str_tuple(value: object) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item or "").strip())
    try:
        payload = json.loads(str(value))
    except Exception:
        return ()
    if not isinstance(payload, list):
        return ()
    return tuple(str(item) for item in payload if str(item or "").strip())
