"""Deterministic rule-based reranking for hybrid retrieval."""

from __future__ import annotations

from typing import Iterable

from .models import RetrievedChunk


_KNOWLEDGE_TYPE_WEIGHTS = {
    "guideline": 0.45,
    "glossary": 0.35,
    "paper_summary": 0.15,
    "general": 0.0,
}


def rerank_candidates(
    *,
    candidates: Iterable[RetrievedChunk],
    query_terms: Iterable[str],
    column_terms: Iterable[str],
    selected_table_id: str = "",
    top_k: int = 4,
) -> tuple[RetrievedChunk, ...]:
    normalized_query_terms = tuple(_normalize_terms(query_terms))
    normalized_column_terms = tuple(_normalize_terms(column_terms))
    normalized_selected_table_id = str(selected_table_id or "").strip().lower()
    reranked: list[RetrievedChunk] = []
    source_hits: dict[str, int] = {}
    for candidate in candidates:
        text = str(candidate.text or "").lower()
        source_name = str(candidate.source_name or "")
        section_title = str(candidate.section_title or "").lower()
        heading_text = " ".join(candidate.heading_path).lower()
        table_headers_text = " ".join(candidate.table_headers).lower()
        numeric_columns_text = " ".join(candidate.table_numeric_columns).lower()
        reasons: list[str] = list(candidate.match_reasons)
        score = 0.0
        if candidate.dense_score is not None:
            score += float(candidate.dense_score) * 1.6
            reasons.append("dense")
        if candidate.keyword_score is not None:
            score += min(float(candidate.keyword_score), 10.0) * 0.35
            reasons.append("keyword")
        query_matches = sum(1 for term in normalized_query_terms if term in text)
        if query_matches:
            score += 0.22 * query_matches
            reasons.append(f"query:{query_matches}")
        column_matches = sum(1 for term in normalized_column_terms if term in text)
        if column_matches:
            score += 0.32 * column_matches
            reasons.append(f"column:{column_matches}")
        header_matches = sum(1 for term in normalized_column_terms if term in table_headers_text or term in numeric_columns_text)
        if header_matches:
            score += 0.42 * header_matches
            reasons.append(f"table_header:{header_matches}")
        knowledge_type = str(candidate.knowledge_type or "general").lower()
        score += _KNOWLEDGE_TYPE_WEIGHTS.get(knowledge_type, 0.0)
        if knowledge_type in _KNOWLEDGE_TYPE_WEIGHTS and knowledge_type != "general":
            reasons.append(knowledge_type)
        chunk_kind = str(candidate.chunk_kind or "text_section").lower()
        if chunk_kind == "table_summary":
            score += 0.28
            reasons.append("table_summary")
        elif chunk_kind == "text_section":
            score += 0.08
            reasons.append("text_section")
        if normalized_selected_table_id and str(candidate.table_id or "").strip().lower() == normalized_selected_table_id:
            score += 0.5
            reasons.append("selected_table")
        if section_title or heading_text:
            section_signal = f"{section_title} {heading_text}"
            if any(term in section_signal for term in ("abstract", "introduction", "background")):
                score += 0.08
                reasons.append("section_context")
            if any(term in section_signal for term in ("results", "discussion", "conclusion")):
                score += 0.06
                reasons.append("section_results")
        if candidate.page_number is not None:
            score += 0.05
            reasons.append("page")
        repeat_penalty = 0.18 * source_hits.get(source_name, 0)
        score -= repeat_penalty
        if repeat_penalty > 0:
            reasons.append("source_penalty")
        reranked.append(
            RetrievedChunk(
                chunk_id=candidate.chunk_id,
                text=candidate.text,
                source_name=candidate.source_name,
                source_path=candidate.source_path,
                knowledge_type=candidate.knowledge_type,
                page_number=candidate.page_number,
                chunk_kind=candidate.chunk_kind,
                section_title=candidate.section_title,
                heading_path=candidate.heading_path,
                table_id=candidate.table_id,
                table_headers=candidate.table_headers,
                table_numeric_columns=candidate.table_numeric_columns,
                content_hint=candidate.content_hint,
                distance=candidate.distance,
                dense_score=candidate.dense_score,
                keyword_score=candidate.keyword_score,
                rerank_score=round(score, 6),
                match_reasons=tuple(_dedupe_preserve_order(reasons)),
            )
        )
        source_hits[source_name] = source_hits.get(source_name, 0) + 1
    reranked.sort(
        key=lambda chunk: (
            float(chunk.rerank_score or 0.0),
            float(chunk.dense_score or 0.0),
            float(chunk.keyword_score or 0.0),
        ),
        reverse=True,
    )
    return tuple(reranked[: max(1, int(top_k))])


def _normalize_terms(terms: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for term in terms:
        clean = str(term or "").strip().lower()
        if not clean or clean in normalized:
            continue
        normalized.append(clean)
    return normalized


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        normalized = str(item or "").strip()
        if not normalized or normalized in deduped:
            continue
        deduped.append(normalized)
    return deduped
