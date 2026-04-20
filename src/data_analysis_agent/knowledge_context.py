"""Lightweight knowledge-context assembly without full RAG infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .data_context import DataContextSummary
from .rag.query_builder import build_retrieval_queries
from .rag.models import RetrievedChunk


@dataclass(frozen=True)
class KnowledgeContextBundle:
    background_context: str = ""
    user_context: str = ""
    success_memory_context: str = ""
    failure_memory_context: str = ""
    reference_context: str = ""
    retrieved_context: str = ""
    retrieved_evidence_register: str = ""

    def render_for_prompt(self) -> str:
        sections: list[str] = []
        if self.user_context:
            sections.append(
                "<User_Intent_Context>\n"
                f"{self.user_context}\n"
                "</User_Intent_Context>"
            )
        if self.success_memory_context:
            sections.append(
                "<Success_Memory_Context>\n"
                f"{self.success_memory_context}\n"
                "</Success_Memory_Context>"
            )
        if self.failure_memory_context:
            sections.append(
                "<Failure_Memory_Context>\n"
                f"{self.failure_memory_context}\n"
                "</Failure_Memory_Context>"
            )
        if self.reference_context:
            sections.append(
                "<Reference_Context>\n"
                f"{self.reference_context}\n"
                "</Reference_Context>"
            )
        if self.retrieved_context:
            sections.append(
                "<Retrieved_Knowledge_Context>\n"
                f"{self.retrieved_context}\n"
                "</Retrieved_Knowledge_Context>"
            )
        if self.retrieved_evidence_register:
            sections.append(
                "<Retrieved_Evidence_Register>\n"
                f"{self.retrieved_evidence_register}\n"
                "</Retrieved_Evidence_Register>"
            )
        return "\n".join(sections).strip()


class KnowledgeContextProvider:
    def __init__(self, *, max_chars_per_reference: int = 1500, max_retrieved_chars: int = 2400) -> None:
        self.max_chars_per_reference = max(200, int(max_chars_per_reference))
        self.max_retrieved_chars = max(600, int(max_retrieved_chars))

    def build_retrieval_query(
        self,
        *,
        data_context: DataContextSummary,
        user_query: str = "",
    ) -> str:
        return build_retrieval_queries(
            data_context=data_context,
            user_query=user_query,
        ).retrieval_query

    def collect(
        self,
        *,
        data_context: DataContextSummary,
        user_query: str = "",
        success_memory_context: str = "",
        failure_memory_context: str = "",
        reference_paths: Iterable[str | Path] = (),
        retrieved_chunks: Iterable[RetrievedChunk] = (),
    ) -> KnowledgeContextBundle:
        reference_chunks: list[str] = []
        for reference_path in reference_paths:
            path = Path(reference_path)
            if not path.exists() or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            normalized = " ".join(text.split()).strip()
            if normalized:
                reference_chunks.append(
                    f"[{path.name}] {normalized[: self.max_chars_per_reference]}"
                )
        retrieved_lines: list[str] = []
        evidence_lines: list[str] = []
        total_chars = 0
        total_evidence_chars = 0
        sorted_chunks = sorted(
            retrieved_chunks,
            key=lambda chunk: (0 if str(chunk.chunk_kind or "") == "table_summary" else 1, -(chunk.score or 0.0)),
        )
        for chunk in sorted_chunks:
            source_label = chunk.source_name or "unknown"
            if chunk.page_number is not None:
                source_label = f"{source_label} | page {chunk.page_number}"
            if chunk.table_id:
                source_label = f"{source_label} | {chunk.table_id}"
            elif chunk.section_title:
                source_label = f"{source_label} | {chunk.section_title}"
            excerpt = " ".join(str(chunk.text or "").split()).strip()
            if not excerpt:
                continue
            line = f"[{source_label}] {excerpt}"
            remaining = self.max_retrieved_chars - total_chars
            if remaining <= 0:
                break
            if len(line) > remaining:
                line = line[:remaining].rstrip() + " ..."
            retrieved_lines.append(line)
            total_chars += len(line)
            if total_chars >= self.max_retrieved_chars:
                break
        for chunk in sorted_chunks:
            excerpt = " ".join(str(chunk.text or "").split()).strip()
            if not excerpt:
                continue
            line = f"{chunk.evidence_id} -> {chunk.citation_label} -> {excerpt}"
            remaining = self.max_retrieved_chars - total_evidence_chars
            if remaining <= 0:
                break
            if len(line) > remaining:
                line = line[:remaining].rstrip() + " ..."
            evidence_lines.append(line)
            total_evidence_chars += len(line)
            if total_evidence_chars >= self.max_retrieved_chars:
                break

        return KnowledgeContextBundle(
            background_context=data_context.background_literature_context,
            user_context=str(user_query or "").strip(),
            success_memory_context=str(success_memory_context or "").strip(),
            failure_memory_context=str(failure_memory_context or "").strip(),
            reference_context="\n".join(reference_chunks).strip(),
            retrieved_context="\n".join(retrieved_lines).strip(),
            retrieved_evidence_register="\n".join(evidence_lines).strip(),
        )
