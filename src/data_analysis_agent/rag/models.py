"""Data models for the lightweight local RAG stack."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re


def _slugify_source_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return normalized or "source"


def _build_source_locator(*, source_name: str, page_number: int | None, table_id: str, section_title: str) -> str:
    parts = [str(source_name or "").strip() or "unknown"]
    if table_id:
        parts.append(table_id)
    elif section_title:
        parts.append(section_title)
    if page_number is not None:
        parts.append(f"p.{page_number}")
    return " | ".join(part for part in parts if part)


def _build_citation_label(*, source_name: str, page_number: int | None, table_id: str, section_title: str) -> str:
    parts = [str(source_name or "").strip() or "unknown"]
    if table_id:
        parts.append(table_id)
    elif section_title and page_number is None:
        parts.append(section_title)
    if page_number is not None:
        parts.append(f"p.{page_number}")
    return f"[来源: {', '.join(part for part in parts if part)}]"


@dataclass(frozen=True)
class KnowledgeDocument:
    doc_id: str
    source_name: str
    source_type: str
    source_path: str
    text: str
    knowledge_type: str = "general"
    page_number: int | None = None
    chunk_kind: str = "text_section"
    section_title: str = ""
    heading_path: tuple[str, ...] = ()
    table_id: str = ""
    table_headers: tuple[str, ...] = ()
    table_numeric_columns: tuple[str, ...] = ()
    content_hint: str = ""


@dataclass(frozen=True)
class KnowledgeChunk:
    doc_id: str
    chunk_id: str
    text: str
    source_name: str
    source_type: str
    source_path: str
    knowledge_type: str = "general"
    page_number: int | None = None
    chunk_kind: str = "text_section"
    section_title: str = ""
    heading_path: tuple[str, ...] = ()
    table_id: str = ""
    table_headers: tuple[str, ...] = ()
    table_numeric_columns: tuple[str, ...] = ()
    content_hint: str = ""

    def to_metadata(self) -> dict[str, str | int]:
        metadata: dict[str, str | int] = {
            "doc_id": self.doc_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "chunk_id": self.chunk_id,
            "knowledge_type": self.knowledge_type,
            "chunk_kind": self.chunk_kind,
        }
        if self.page_number is not None:
            metadata["page_number"] = int(self.page_number)
        if self.section_title:
            metadata["section_title"] = self.section_title
        if self.heading_path:
            metadata["heading_path"] = json.dumps(list(self.heading_path), ensure_ascii=False)
        if self.table_id:
            metadata["table_id"] = self.table_id
        if self.table_headers:
            metadata["table_headers"] = json.dumps(list(self.table_headers), ensure_ascii=False)
        if self.table_numeric_columns:
            metadata["table_numeric_columns"] = json.dumps(list(self.table_numeric_columns), ensure_ascii=False)
        if self.content_hint:
            metadata["content_hint"] = self.content_hint[:500]
        return metadata


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    source_name: str
    source_path: str
    knowledge_type: str = "general"
    page_number: int | None = None
    chunk_kind: str = "text_section"
    section_title: str = ""
    heading_path: tuple[str, ...] = ()
    table_id: str = ""
    table_headers: tuple[str, ...] = ()
    table_numeric_columns: tuple[str, ...] = ()
    content_hint: str = ""
    distance: float | None = None
    dense_score: float | None = None
    keyword_score: float | None = None
    rerank_score: float | None = None
    match_reasons: tuple[str, ...] = ()
    evidence_id: str = ""
    citation_label: str = ""
    source_locator: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_id:
            object.__setattr__(
                self,
                "evidence_id",
                f"RAG-{_slugify_source_name(self.source_name)}-{self.chunk_id}",
            )
        if not self.source_locator:
            object.__setattr__(
                self,
                "source_locator",
                _build_source_locator(
                    source_name=self.source_name,
                    page_number=self.page_number,
                    table_id=self.table_id,
                    section_title=self.section_title,
                ),
            )
        if not self.citation_label:
            object.__setattr__(
                self,
                "citation_label",
                _build_citation_label(
                    source_name=self.source_name,
                    page_number=self.page_number,
                    table_id=self.table_id,
                    section_title=self.section_title,
                ),
            )

    @property
    def score(self) -> float | None:
        if self.rerank_score is not None:
            return self.rerank_score
        if self.dense_score is not None:
            return self.dense_score
        if self.distance is None:
            return None
        try:
            return 1.0 / (1.0 + float(self.distance))
        except Exception:
            return None

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "source_name": self.source_name,
            "source_path": self.source_path,
            "knowledge_type": self.knowledge_type,
            "page_number": self.page_number,
            "chunk_kind": self.chunk_kind,
            "section_title": self.section_title,
            "heading_path": list(self.heading_path),
            "table_id": self.table_id,
            "table_headers": list(self.table_headers),
            "table_numeric_columns": list(self.table_numeric_columns),
            "content_hint": self.content_hint[:240],
            "distance": self.distance,
            "dense_score": self.dense_score,
            "keyword_score": self.keyword_score,
            "rerank_score": self.rerank_score,
            "score": self.score,
            "match_reasons": list(self.match_reasons),
            "evidence_id": self.evidence_id,
            "citation_label": self.citation_label,
            "source_locator": self.source_locator,
            "text_excerpt": self.text[:320],
        }


@dataclass(frozen=True)
class RagIndexResult:
    status: str
    indexed_documents: tuple[str, ...] = ()
    indexed_chunk_count: int = 0
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RagRetrievalResult:
    status: str
    retrieval_query: str = ""
    dense_query: str = ""
    keyword_query: str = ""
    chunks: tuple[RetrievedChunk, ...] = ()
    dense_candidates: tuple[RetrievedChunk, ...] = ()
    keyword_candidates: tuple[RetrievedChunk, ...] = ()
    ephemeral_table_candidates: tuple[RetrievedChunk, ...] = ()
    reranked_chunks: tuple[RetrievedChunk, ...] = ()
    retrieval_strategy: str = "dense_only"
    table_candidate_count: int = 0
    warnings: tuple[str, ...] = ()

    @property
    def match_count(self) -> int:
        return len(self.reranked_chunks or self.chunks)

    @property
    def dense_match_count(self) -> int:
        return len(self.dense_candidates)

    @property
    def keyword_match_count(self) -> int:
        return len(self.keyword_candidates)

    @property
    def source_names(self) -> tuple[str, ...]:
        names: list[str] = []
        for chunk in (self.reranked_chunks or self.chunks):
            if chunk.source_name not in names:
                names.append(chunk.source_name)
        return tuple(names)

    @property
    def structured_match_count(self) -> int:
        return sum(
            1
            for chunk in (self.reranked_chunks or self.chunks)
            if str(chunk.chunk_kind or "").strip() in {"text_section", "table_summary"}
        )
