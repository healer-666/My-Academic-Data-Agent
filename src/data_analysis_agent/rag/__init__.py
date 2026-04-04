"""Local RAG exports with lazy imports for dependency-light environments."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "KnowledgeChunk",
    "KnowledgeDocument",
    "RagIndexResult",
    "RagRetrievalResult",
    "RagService",
    "RetrievedChunk",
]


_EXPORT_MAP = {
    "KnowledgeChunk": ("data_analysis_agent.rag.models", "KnowledgeChunk"),
    "KnowledgeDocument": ("data_analysis_agent.rag.models", "KnowledgeDocument"),
    "RagIndexResult": ("data_analysis_agent.rag.models", "RagIndexResult"),
    "RagRetrievalResult": ("data_analysis_agent.rag.models", "RagRetrievalResult"),
    "RagService": ("data_analysis_agent.rag.service", "RagService"),
    "RetrievedChunk": ("data_analysis_agent.rag.models", "RetrievedChunk"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError(name)
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
