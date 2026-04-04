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
    reference_context: str = ""
    retrieved_context: str = ""

    def render_for_prompt(self) -> str:
        sections: list[str] = []
        if self.user_context:
            sections.append(
                "<User_Intent_Context>\n"
                f"{self.user_context}\n"
                "</User_Intent_Context>"
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
        total_chars = 0
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

        return KnowledgeContextBundle(
            background_context=data_context.background_literature_context,
            user_context=str(user_query or "").strip(),
            reference_context="\n".join(reference_chunks).strip(),
            retrieved_context="\n".join(retrieved_lines).strip(),
        )
