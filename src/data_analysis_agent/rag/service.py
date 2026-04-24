"""High-level local RAG orchestration service."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

from ..config import RuntimeConfig
from .document_reader import chunk_documents, load_knowledge_documents
from .embeddings import OpenAIEmbeddingClient
from .keyword_index import KeywordIndexStore
from .models import RagIndexResult, RagRetrievalResult, RetrievedChunk
from .query_builder import RetrievalQueryBundle, build_retrieval_queries
from .reranker import rerank_candidates
from .vector_store import ChromaVectorStore


class RagService:
    COLLECTION_NAME = "academic_data_agent_knowledge"

    def __init__(
        self,
        *,
        runtime_config: RuntimeConfig,
        knowledge_base_dir: str | Path | None = None,
    ) -> None:
        self.runtime_config = runtime_config
        self.knowledge_base_dir = Path(knowledge_base_dir or Path("memory") / "knowledge_base").resolve()
        self.files_dir = self.knowledge_base_dir / "files"
        self.chroma_dir = self.knowledge_base_dir / "chroma"
        self.keyword_index_path = self.knowledge_base_dir / "keyword_index.json"
        self.embedding_client = OpenAIEmbeddingClient(
            model_id=runtime_config.embedding_model_id or "",
            api_key=runtime_config.embedding_api_key or "",
            base_url=runtime_config.embedding_base_url or "",
            timeout=runtime_config.embedding_timeout,
        )
        self.vector_store = ChromaVectorStore(
            persist_dir=self.chroma_dir,
            collection_name=self.COLLECTION_NAME,
        )
        self.keyword_index = KeywordIndexStore(persist_path=self.keyword_index_path)

    def index_files(self, knowledge_paths: Iterable[str | Path]) -> RagIndexResult:
        warnings: list[str] = []
        indexed_documents: list[str] = []
        total_chunks = 0
        for source_path in knowledge_paths:
            if source_path in (None, ""):
                continue
            source = Path(source_path)
            if not source.exists() or not source.is_file():
                warnings.append(f"Knowledge file does not exist: {source}")
                continue
            copied_path = self._copy_into_knowledge_base(source)
            documents, document_warnings = load_knowledge_documents(copied_path)
            warnings.extend(document_warnings)
            if not documents:
                continue
            chunks = chunk_documents(documents)
            if not chunks:
                warnings.append(f"Knowledge file {source.name} produced no chunks after splitting.")
                continue
            doc_id = documents[0].doc_id
            chunk_count = 0
            if self.runtime_config.embedding_configured:
                embeddings = self.embedding_client.embed_texts(chunk.text for chunk in chunks)
                if len(embeddings) != len(chunks):
                    raise ValueError(f"Embedding response count mismatch for {source.name}.")
                chunk_count = self.vector_store.replace_document(
                    doc_id=doc_id,
                    chunks=chunks,
                    embeddings=embeddings,
                )
            else:
                warnings.append(
                    f"Embedding configuration is incomplete; indexed {source.name} for keyword retrieval only."
                )
            self.keyword_index.replace_document(
                doc_id=doc_id,
                chunks=chunks,
            )
            if chunk_count or chunks:
                indexed_documents.append(source.name)
                total_chunks += chunk_count or len(chunks)
        status = "completed" if indexed_documents else "skipped"
        return RagIndexResult(
            status=status,
            indexed_documents=tuple(indexed_documents),
            indexed_chunk_count=total_chunks,
            warnings=tuple(warnings),
        )

    def build_queries(
        self,
        *,
        data_context,
        user_query: str = "",
    ) -> RetrievalQueryBundle:
        return build_retrieval_queries(
            data_context=data_context,
            user_query=user_query,
        )

    def retrieve(
        self,
        *,
        retrieval_query: str = "",
        top_k: int = 4,
        dense_query: str = "",
        keyword_query: str = "",
        query_terms: Iterable[str] = (),
        column_terms: Iterable[str] = (),
        selected_table_id: str = "",
        ephemeral_candidates: Iterable[RetrievedChunk] = (),
        dense_top_k: int = 8,
        keyword_top_k: int = 8,
    ) -> RagRetrievalResult:
        normalized_dense_query = str(dense_query or retrieval_query or "").strip()
        normalized_keyword_query = str(keyword_query or retrieval_query or "").strip()
        normalized_retrieval_query = str(retrieval_query or normalized_dense_query or normalized_keyword_query).strip()
        if not normalized_retrieval_query:
            return RagRetrievalResult(
                status="skipped",
                warnings=("Retrieval query is empty.",),
                retrieval_strategy="hybrid",
            )
        dense_candidates: tuple[RetrievedChunk, ...] = ()
        keyword_candidates: tuple[RetrievedChunk, ...] = ()
        ephemeral_table_candidates = tuple(ephemeral_candidates)
        warnings: list[str] = []
        dense_available = False
        try:
            dense_available = self.vector_store.count() > 0
        except Exception as exc:
            warnings.append(f"Dense index status check failed: {exc}")

        if dense_available:
            try:
                embeddings = self.embedding_client.embed_texts([normalized_dense_query])
                query_embedding = embeddings[0] if embeddings else []
                dense_candidates = self.vector_store.query(
                    query_embedding=query_embedding,
                    top_k=dense_top_k,
                )
            except Exception as exc:
                warnings.append(f"Dense retrieval failed: {exc}")

        try:
            keyword_candidates = self.keyword_index.query(
                keyword_query=normalized_keyword_query,
                top_k=keyword_top_k,
            )
        except Exception as exc:
            warnings.append(f"Keyword retrieval failed: {exc}")

        merged_candidates = _merge_candidates(dense_candidates, keyword_candidates, ephemeral_table_candidates)
        reranked = rerank_candidates(
            candidates=merged_candidates,
            query_terms=query_terms,
            column_terms=column_terms,
            selected_table_id=selected_table_id,
            top_k=top_k,
        )
        status = "retrieved" if reranked else ("no_matches" if merged_candidates else "empty")
        return RagRetrievalResult(
            status=status,
            retrieval_query=normalized_retrieval_query,
            dense_query=normalized_dense_query,
            keyword_query=normalized_keyword_query,
            chunks=reranked,
            dense_candidates=dense_candidates,
            keyword_candidates=keyword_candidates,
            ephemeral_table_candidates=ephemeral_table_candidates,
            reranked_chunks=reranked,
            retrieval_strategy="hybrid",
            table_candidate_count=len(ephemeral_table_candidates),
            warnings=tuple(warnings),
        )

    def build_ephemeral_table_candidates(self, *, data_context) -> tuple[RetrievedChunk, ...]:
        parsed_document_path = getattr(data_context, "parsed_document_path", None)
        if parsed_document_path in (None, ""):
            return ()
        path = Path(parsed_document_path)
        if not path.exists():
            return ()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return ()
        if not isinstance(payload, dict):
            return ()
        source_pdf = Path(str(payload.get("source_pdf", "") or "")).name or path.name
        selected_table_id = str(payload.get("selected_table_id", "") or getattr(data_context, "selected_table_id", "")).strip()
        candidate_tables = payload.get("candidate_table_summaries", payload.get("candidate_tables", []))
        if not isinstance(candidate_tables, list):
            return ()
        candidates: list[RetrievedChunk] = []
        for candidate in candidate_tables:
            if not isinstance(candidate, dict):
                continue
            table_id = str(candidate.get("table_id", "") or "").strip()
            if not table_id:
                continue
            headers = _normalize_str_tuple(candidate.get("headers", []))
            numeric_columns = _normalize_str_tuple(candidate.get("numeric_columns", []))
            content_hint = str(candidate.get("content_hint", "") or "").strip()
            page_number = _coerce_optional_int(candidate.get("page_number"))
            summary_text = _build_ephemeral_table_text(
                table_id=table_id,
                page_number=page_number,
                headers=headers,
                numeric_columns=numeric_columns,
                content_hint=content_hint,
                selected=(table_id == selected_table_id),
            )
            match_reasons = ("ephemeral_table", "selected_table") if table_id == selected_table_id else ("ephemeral_table",)
            candidates.append(
                RetrievedChunk(
                    chunk_id=f"ephemeral-{table_id}",
                    text=summary_text,
                    source_name=source_pdf,
                    source_path=path.as_posix(),
                    knowledge_type="general",
                    page_number=page_number,
                    chunk_kind="table_summary",
                    section_title=f"Table {table_id}",
                    heading_path=(f"Table {table_id}",),
                    table_id=table_id,
                    table_headers=headers,
                    table_numeric_columns=numeric_columns,
                    content_hint=content_hint,
                    match_reasons=match_reasons,
                )
            )
        return tuple(candidates)

    def _copy_into_knowledge_base(self, source: Path) -> Path:
        self.files_dir.mkdir(parents=True, exist_ok=True)
        destination = self.files_dir / source.name
        if destination.resolve() != source.resolve():
            shutil.copy2(source, destination)
        return destination


def _merge_candidates(
    dense_candidates: Iterable[RetrievedChunk],
    keyword_candidates: Iterable[RetrievedChunk],
    ephemeral_candidates: Iterable[RetrievedChunk] = (),
) -> tuple[RetrievedChunk, ...]:
    ordered_candidates = (*tuple(dense_candidates), *tuple(keyword_candidates), *tuple(ephemeral_candidates))
    merged: dict[str, RetrievedChunk] = {}
    for candidate in ordered_candidates:
        existing = merged.get(candidate.chunk_id)
        if existing is None:
            merged[candidate.chunk_id] = candidate
            continue
        merged[candidate.chunk_id] = RetrievedChunk(
            chunk_id=existing.chunk_id,
            text=existing.text or candidate.text,
            source_name=existing.source_name or candidate.source_name,
            source_path=existing.source_path or candidate.source_path,
            knowledge_type=existing.knowledge_type or candidate.knowledge_type,
            page_number=existing.page_number if existing.page_number is not None else candidate.page_number,
            chunk_kind=existing.chunk_kind or candidate.chunk_kind,
            section_title=existing.section_title or candidate.section_title,
            heading_path=existing.heading_path or candidate.heading_path,
            table_id=existing.table_id or candidate.table_id,
            table_headers=existing.table_headers or candidate.table_headers,
            table_numeric_columns=existing.table_numeric_columns or candidate.table_numeric_columns,
            content_hint=existing.content_hint or candidate.content_hint,
            distance=existing.distance if existing.distance is not None else candidate.distance,
            dense_score=existing.dense_score if existing.dense_score is not None else candidate.dense_score,
            keyword_score=candidate.keyword_score if candidate.keyword_score is not None else existing.keyword_score,
            rerank_score=existing.rerank_score if existing.rerank_score is not None else candidate.rerank_score,
            match_reasons=tuple(dict.fromkeys((*existing.match_reasons, *candidate.match_reasons))),
        )
    return tuple(merged.values())


def _normalize_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item or "").strip())


def _coerce_optional_int(value: object) -> int | None:
    try:
        return None if value in (None, "") else int(value)
    except Exception:
        return None


def _build_ephemeral_table_text(
    *,
    table_id: str,
    page_number: int | None,
    headers: tuple[str, ...],
    numeric_columns: tuple[str, ...],
    content_hint: str,
    selected: bool,
) -> str:
    page_text = f"page {page_number}" if page_number is not None else "page unknown"
    return " ".join(
        part
        for part in (
            f"Ephemeral table summary for {table_id} ({page_text}).",
            "Selected primary table." if selected else "Auxiliary candidate table.",
            f"Headers: {', '.join(headers) or 'none'}.",
            f"Numeric columns: {', '.join(numeric_columns) or 'none'}.",
            f"Content hint: {content_hint or 'none'}.",
        )
        if part
    ).strip()
