"""DataAnalysisAgent package with lazy exports for dependency-light imports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "AnalysisRunResult",
    "DataContextSummary",
    "PythonInterpreterTool",
    "RuntimeConfig",
    "ScientificReActRunner",
    "TavilySearchTool",
    "apply_token_counter_patch",
    "build_data_context",
    "load_runtime_config",
    "render_diagnostics",
    "render_full_report",
    "render_trace_table",
    "run_analysis",
]


_EXPORT_MAP = {
    "AnalysisRunResult": ("data_analysis_agent.agent_runner", "AnalysisRunResult"),
    "ScientificReActRunner": ("data_analysis_agent.agent_runner", "ScientificReActRunner"),
    "run_analysis": ("data_analysis_agent.agent_runner", "run_analysis"),
    "RuntimeConfig": ("data_analysis_agent.config", "RuntimeConfig"),
    "apply_token_counter_patch": ("data_analysis_agent.config", "apply_token_counter_patch"),
    "load_runtime_config": ("data_analysis_agent.config", "load_runtime_config"),
    "DataContextSummary": ("data_analysis_agent.data_context", "DataContextSummary"),
    "build_data_context": ("data_analysis_agent.data_context", "build_data_context"),
    "render_diagnostics": ("data_analysis_agent.presentation", "render_diagnostics"),
    "render_full_report": ("data_analysis_agent.presentation", "render_full_report"),
    "render_trace_table": ("data_analysis_agent.presentation", "render_trace_table"),
    "PythonInterpreterTool": ("data_analysis_agent.tools.python_interpreter", "PythonInterpreterTool"),
    "TavilySearchTool": ("data_analysis_agent.tools.tavily_search", "TavilySearchTool"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError(name)
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
