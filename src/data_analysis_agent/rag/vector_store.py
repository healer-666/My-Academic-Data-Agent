"""Chroma-backed vector storage for local knowledge documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import KnowledgeChunk, RetrievedChunk


class ChromaVectorStore:
    def __init__(self, *, persist_dir: str | Path, collection_name: str) -> None:
        self.persist_dir = Path(persist_dir).resolve()
        self.collection_name = collection_name

    def count(self) -> int:
        collection = self._get_collection()
        return int(collection.count())

    def replace_document(
        self,
        *,
        doc_id: str,
        chunks: Iterable[KnowledgeChunk],
        embeddings: Iterable[list[float]],
    ) -> int:
        collection = self._get_collection()
        chunk_list = list(chunks)
        embedding_list = list(embeddings)
        if not chunk_list:
            return 0
        if len(chunk_list) != len(embedding_list):
            raise ValueError("Chunk and embedding counts do not match.")
        try:
            collection.delete(where={"doc_id": doc_id})
        except Exception:
            pass
        collection.upsert(
            ids=[chunk.chunk_id for chunk in chunk_list],
            documents=[chunk.text for chunk in chunk_list],
            metadatas=[chunk.to_metadata() for chunk in chunk_list],
            embeddings=embedding_list,
        )
        return len(chunk_list)

    def query(self, *, query_embedding: list[float], top_k: int = 4) -> tuple[RetrievedChunk, ...]:
        if not query_embedding:
            return ()
        collection = self._get_collection()
        if int(collection.count()) <= 0:
            return ()
        payload = collection.query(
            query_embeddings=[query_embedding],
            n_results=max(1, int(top_k)),
            include=["documents", "metadatas", "distances"],
        )
        documents = payload.get("documents", [[]])
        metadatas = payload.get("metadatas", [[]])
        distances = payload.get("distances", [[]])
        results: list[RetrievedChunk] = []
        for index, text in enumerate(documents[0] if documents else []):
            metadata = (metadatas[0] if metadatas else [])[index] if metadatas else {}
            distance = (distances[0] if distances else [])[index] if distances else None
            if not isinstance(metadata, dict):
                metadata = {}
            results.append(
                RetrievedChunk(
                    chunk_id=str(metadata.get("chunk_id", "") or ""),
                    text=str(text or ""),
                    source_name=str(metadata.get("source_name", "") or "unknown"),
                    source_path=str(metadata.get("source_path", "") or ""),
                    knowledge_type=str(metadata.get("knowledge_type", "") or "general"),
                    page_number=_coerce_optional_int(metadata.get("page_number")),
                    chunk_kind=str(metadata.get("chunk_kind", "") or "text_section"),
                    section_title=str(metadata.get("section_title", "") or ""),
                    heading_path=_coerce_str_tuple(metadata.get("heading_path")),
                    table_id=str(metadata.get("table_id", "") or ""),
                    table_headers=_coerce_str_tuple(metadata.get("table_headers")),
                    table_numeric_columns=_coerce_str_tuple(metadata.get("table_numeric_columns")),
                    content_hint=str(metadata.get("content_hint", "") or ""),
                    distance=_coerce_optional_float(distance),
                    dense_score=_distance_to_score(distance),
                )
            )
        return tuple(results)

    def _get_collection(self):
        try:
            import chromadb
        except Exception as exc:
            raise RuntimeError(f"chromadb is unavailable: {exc}") from exc
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self.persist_dir))
        return client.get_or_create_collection(name=self.collection_name)


def _coerce_optional_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except Exception:
        return None


def _distance_to_score(value: object) -> float | None:
    distance = _coerce_optional_float(value)
    if distance is None:
        return None
    try:
        return 1.0 / (1.0 + float(distance))
    except Exception:
        return None


def _coerce_optional_int(value: object) -> int | None:
    try:
        return None if value in (None, "") else int(value)
    except Exception:
        return None


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
