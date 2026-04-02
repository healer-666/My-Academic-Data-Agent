"""Tool registry construction and execution helpers."""

from __future__ import annotations

import contextlib
import io
import json
import time
from typing import Any

from .compat import ToolRegistry
from .reporting import ReportTelemetry
from .runtime_models import AgentStepTrace, ToolExecutionRecord
from .tools.python_interpreter import PythonInterpreterTool
from .tools.tavily_search import TavilySearchTool


def build_tool_registry(*, enable_search: bool = True) -> ToolRegistry:
    tool_registry = ToolRegistry()
    for deprecated_tool_name in ("DataCleaningTool", "DataStatisticsTool", "python_interpreter_tool"):
        tool_registry._tools.pop(deprecated_tool_name, None)
        tool_registry._functions.pop(deprecated_tool_name, None)

    with contextlib.redirect_stdout(io.StringIO()):
        tool_registry.register_tool(PythonInterpreterTool())
        if enable_search:
            tool_registry.register_tool(TavilySearchTool())
    return tool_registry


def parse_tool_observation(observation: str) -> tuple[str, str]:
    try:
        payload = json.loads(observation)
    except Exception:
        preview = " ".join(observation.split())
        return "unknown", preview[:220]

    status = str(payload.get("status", "unknown")).strip() or "unknown"
    preview = " ".join(str(payload.get("text", "")).split())
    return status, preview[:220]


def execute_tool_call(
    *,
    tool_registry: Any,
    tool_name: str,
    tool_input: str,
    available_tools: set[str] | None = None,
) -> ToolExecutionRecord:
    available = available_tools or set(tool_registry.list_tools())
    if tool_name not in available:
        observation = json.dumps(
            {
                "status": "error",
                "text": f"Tool '{tool_name}' is not registered.",
                "available_tools": sorted(available),
            },
            ensure_ascii=False,
            indent=2,
        )
        tool_status, observation_preview = parse_tool_observation(observation)
        return ToolExecutionRecord(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_status=tool_status,
            observation=observation,
            observation_preview=observation_preview,
            duration_ms=0,
        )

    started_at = time.perf_counter()
    observation = tool_registry.execute_tool(tool_name, tool_input)
    duration_ms = int(round((time.perf_counter() - started_at) * 1000))
    tool_status, observation_preview = parse_tool_observation(observation)
    return ToolExecutionRecord(
        tool_name=tool_name,
        tool_input=tool_input,
        tool_status=tool_status,
        observation=observation,
        observation_preview=observation_preview,
        duration_ms=duration_ms,
    )


def determine_search_status(step_traces: tuple[AgentStepTrace, ...], telemetry: ReportTelemetry) -> tuple[str, str]:
    tavily_steps = [trace for trace in step_traces if trace.tool_name == "TavilySearchTool"]
    if telemetry.valid and telemetry.search_used:
        return "used", telemetry.search_notes
    if not tavily_steps:
        if telemetry.valid and telemetry.search_notes != "unknown":
            return "not_used", telemetry.search_notes
        return "not_used", "No online knowledge retrieval was triggered."

    combined_preview = " ".join(trace.observation_preview for trace in tavily_steps).lower()
    if "no tavily search credential" in combined_preview:
        return "skipped", "Tavily credential is not configured, so online search was skipped."
    if "temporarily unavailable" in combined_preview or "dependency is unavailable" in combined_preview:
        return "unavailable", "Online retrieval was unavailable; the agent fell back to local analysis."
    if any(trace.tool_status == "success" for trace in tavily_steps):
        return "used", telemetry.search_notes if telemetry.search_notes != "unknown" else "Online search results were incorporated."
    return "attempted", telemetry.search_notes if telemetry.search_notes != "unknown" else "Online search was attempted but did not yield stable results."


def collect_tools_used(step_traces: tuple[AgentStepTrace, ...], telemetry: ReportTelemetry) -> tuple[str, ...]:
    if telemetry.tools_used:
        return telemetry.tools_used
    tool_names: list[str] = []
    for trace in step_traces:
        if trace.tool_name and trace.tool_name not in tool_names:
            tool_names.append(trace.tool_name)
    return tuple(tool_names)
