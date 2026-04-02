"""Gradio-based web demo layer with lazy exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "build_demo",
    "default_max_reviews_for_quality",
    "stream_analysis_session",
]


_EXPORT_MAP = {
    "build_demo": ("data_analysis_agent.web.app", "build_demo"),
    "default_max_reviews_for_quality": ("data_analysis_agent.web.service", "default_max_reviews_for_quality"),
    "stream_analysis_session": ("data_analysis_agent.web.service", "stream_analysis_session"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError(name)
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
