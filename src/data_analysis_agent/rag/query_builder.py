"""Deterministic query rewriting for local RAG retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from ..data_context import DataContextSummary


_EN_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "what",
    "when",
    "where",
    "which",
    "please",
    "about",
    "data",
    "report",
    "analysis",
}
_CN_STOPWORDS = {"请", "分析", "这个", "数据", "报告", "以及", "相关", "说明"}


@dataclass(frozen=True)
class RetrievalQueryBundle:
    retrieval_query: str
    dense_query: str
    keyword_query: str
    normalized_terms: tuple[str, ...] = ()


def build_retrieval_queries(
    *,
    data_context: DataContextSummary,
    user_query: str = "",
) -> RetrievalQueryBundle:
    columns = tuple(str(column).strip() for column in data_context.columns[:8] if str(column).strip())
    selected_headers = tuple(
        str(column).strip()
        for column in getattr(data_context, "selected_table_headers", ())[:8]
        if str(column).strip()
    )
    selected_numeric_columns = tuple(
        str(column).strip()
        for column in getattr(data_context, "selected_table_numeric_columns", ())[:8]
        if str(column).strip()
    )
    candidate_signals = [
        str(data_context.selected_table_id or "").strip(),
        ", ".join(selected_headers),
        ", ".join(selected_numeric_columns),
        str(data_context.candidate_table_summaries_text or "").strip()[:240],
        str(data_context.background_literature_context or "").strip()[:300],
    ]
    dense_parts = [
        _normalize_sentence(user_query),
        ", ".join(columns),
        *[_normalize_sentence(signal) for signal in candidate_signals if signal],
    ]
    dense_query = " | ".join(part for part in dense_parts if part).strip()

    keyword_terms: list[str] = []
    keyword_terms.extend(_extract_query_terms(user_query))
    for column in columns:
        keyword_terms.extend(_extract_query_terms(column))
    for signal in candidate_signals:
        keyword_terms.extend(_extract_query_terms(signal))
    deduped_terms = tuple(_dedupe_terms(keyword_terms))
    keyword_query = " ".join(deduped_terms).strip()
    retrieval_query = dense_query or keyword_query
    return RetrievalQueryBundle(
        retrieval_query=retrieval_query,
        dense_query=dense_query,
        keyword_query=keyword_query,
        normalized_terms=deduped_terms,
    )


def _normalize_sentence(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def _extract_query_terms(text: str) -> list[str]:
    normalized = _normalize_sentence(text)
    if not normalized:
        return []
    raw_terms = re.findall(
        r"[A-Za-z0-9_\-/+]*[\u4e00-\u9fff]+[A-Za-z0-9_\-/+]*|[A-Za-z0-9_\-/+]+|[\u4e00-\u9fff]{1,}",
        normalized,
    )
    terms: list[str] = []
    for term in raw_terms:
        for candidate in _expand_term_variants(term):
            cleaned = candidate.strip(" _-/+").lower()
            if len(cleaned) <= 1:
                continue
            if cleaned in _EN_STOPWORDS or cleaned in _CN_STOPWORDS:
                continue
            if re.fullmatch(r"\d+", cleaned):
                continue
            if cleaned not in terms:
                terms.append(cleaned)
    return terms


def _dedupe_terms(terms: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    for term in terms:
        normalized = str(term or "").strip().lower()
        if not normalized or normalized in deduped:
            continue
        deduped.append(normalized)
    return deduped


def _expand_term_variants(term: str) -> list[str]:
    normalized = str(term or "").strip()
    if not normalized:
        return []
    variants = [normalized]
    if re.search(r"[A-Za-z]", normalized) and re.search(r"[\u4e00-\u9fff]", normalized):
        variants.extend(re.findall(r"[A-Za-z0-9_\-/+]+|[\u4e00-\u9fff]{1,}", normalized))
    deduped: list[str] = []
    for variant in variants:
        cleaned = str(variant or "").strip()
        if not cleaned or cleaned in deduped:
            continue
        deduped.append(cleaned)
    return deduped
