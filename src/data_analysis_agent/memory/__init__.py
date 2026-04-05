"""Project memory exports with lazy imports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "MemoryRecord",
    "MemoryRetrievalResult",
    "MemoryWriteResult",
    "ProjectMemoryService",
    "derive_memory_scope_key",
    "extract_memory_records",
]


_EXPORT_MAP = {
    "MemoryRecord": ("data_analysis_agent.memory.models", "MemoryRecord"),
    "MemoryRetrievalResult": ("data_analysis_agent.memory.models", "MemoryRetrievalResult"),
    "MemoryWriteResult": ("data_analysis_agent.memory.models", "MemoryWriteResult"),
    "ProjectMemoryService": ("data_analysis_agent.memory.service", "ProjectMemoryService"),
    "derive_memory_scope_key": ("data_analysis_agent.memory.scope", "derive_memory_scope_key"),
    "extract_memory_records": ("data_analysis_agent.memory.extractor", "extract_memory_records"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError(name)
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
