"""Lightweight knowledge-context assembly without full RAG infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .data_context import DataContextSummary


@dataclass(frozen=True)
class KnowledgeContextBundle:
    background_context: str = ""
    user_context: str = ""
    reference_context: str = ""

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
        return "\n".join(sections).strip()


class KnowledgeContextProvider:
    def __init__(self, *, max_chars_per_reference: int = 1500) -> None:
        self.max_chars_per_reference = max(200, int(max_chars_per_reference))

    def collect(
        self,
        *,
        data_context: DataContextSummary,
        user_query: str = "",
        reference_paths: Iterable[str | Path] = (),
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

        return KnowledgeContextBundle(
            background_context=data_context.background_literature_context,
            user_context=str(user_query or "").strip(),
            reference_context="\n".join(reference_chunks).strip(),
        )
