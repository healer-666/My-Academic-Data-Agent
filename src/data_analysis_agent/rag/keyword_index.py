"""Lightweight persistent keyword retrieval for hybrid RAG."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .models import KnowledgeChunk, RetrievedChunk


class KeywordIndexStore:
    def __init__(self, *, persist_path: str | Path) -> None:
        self.persist_path = Path(persist_path).resolve()

    def replace_document(self, *, doc_id: str, chunks: Iterable[KnowledgeChunk]) -> int:
        payload = self._load_payload()
        chunk_list = list(chunks)
        if not chunk_list:
            return 0
        payload["chunks"] = [item for item in payload.get("chunks", []) if str(item.get("doc_id", "")) != doc_id]
        for chunk in chunk_list:
            payload["chunks"].append(
                {
                    "doc_id": chunk.doc_id,
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "source_name": chunk.source_name,
                    "source_path": chunk.source_path,
                    "source_type": chunk.source_type,
                    "knowledge_type": chunk.knowledge_type,
                    "page_number": chunk.page_number,
                    "tokens": _tokenize_text(chunk.text),
                }
            )
        self._save_payload(payload)
        return len(chunk_list)

    def query(self, *, keyword_query: str, top_k: int = 8) -> tuple[RetrievedChunk, ...]:
        tokens = _tokenize_text(keyword_query)
        if not tokens:
            return ()
        payload = self._load_payload()
        entries = payload.get("chunks", [])
        if not isinstance(entries, list) or not entries:
            return ()
        doc_freq: dict[str, int] = {}
        for token in tokens:
            doc_freq[token] = sum(
                1
                for entry in entries
                if token in entry.get("tokens", [])
            )
        total_docs = max(1, len(entries))
        scored: list[tuple[float, dict[str, object]]] = []
        for entry in entries:
            entry_tokens = entry.get("tokens", [])
            if not isinstance(entry_tokens, list):
                continue
            score = 0.0
            token_set = set(str(item) for item in entry_tokens)
            for token in tokens:
                if token not in token_set:
                    continue
                tf = entry_tokens.count(token)
                idf = math.log((1 + total_docs) / (1 + doc_freq.get(token, 0))) + 1.0
                score += float(tf) * float(idf)
            if score <= 0:
                continue
            scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[RetrievedChunk] = []
        for score, entry in scored[: max(1, int(top_k))]:
            results.append(
                RetrievedChunk(
                    chunk_id=str(entry.get("chunk_id", "") or ""),
                    text=str(entry.get("text", "") or ""),
                    source_name=str(entry.get("source_name", "") or "unknown"),
                    source_path=str(entry.get("source_path", "") or ""),
                    knowledge_type=str(entry.get("knowledge_type", "") or "general"),
                    page_number=_coerce_optional_int(entry.get("page_number")),
                    keyword_score=round(score, 6),
                )
            )
        return tuple(results)

    def _load_payload(self) -> dict[str, object]:
        if not self.persist_path.exists():
            return {"chunks": []}
        try:
            payload = json.loads(self.persist_path.read_text(encoding="utf-8"))
        except Exception:
            return {"chunks": []}
        if not isinstance(payload, dict):
            return {"chunks": []}
        payload.setdefault("chunks", [])
        return payload

    def _save_payload(self, payload: dict[str, object]) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self.persist_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _tokenize_text(text: str) -> list[str]:
    normalized = " ".join(str(text or "").split()).strip().lower()
    if not normalized:
        return []
    return re.findall(r"[a-z0-9_\-/+]+|[\u4e00-\u9fff]{2,}", normalized)


def _coerce_optional_int(value: object) -> int | None:
    try:
        return None if value in (None, "") else int(value)
    except Exception:
        return None
