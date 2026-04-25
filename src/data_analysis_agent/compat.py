"""Compatibility shims for optional third-party runtime dependencies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


HELLO_AGENTS_AVAILABLE = True
HELLO_AGENTS_IMPORT_ERROR: Exception | None = None

try:  # pragma: no cover - exercised indirectly when dependency exists
    from hello_agents import HelloAgentsLLM, ToolRegistry
    from hello_agents.tools import Tool, ToolParameter
except Exception as exc:  # pragma: no cover - fallback used in dependency-light tests
    HELLO_AGENTS_AVAILABLE = False
    HELLO_AGENTS_IMPORT_ERROR = exc

    @dataclass(frozen=True)
    class ToolParameter:
        name: str
        type: str
        description: str
        required: bool = False


    class Tool:
        def __init__(self, *, name: str, description: str = "") -> None:
            self.name = name
            self.description = description

        def get_parameters(self) -> list[ToolParameter]:
            return []

        def execute(self, parameters: dict[str, Any]) -> Any:
            raise NotImplementedError

        def run(self, parameters: dict[str, Any]) -> str:
            result = self.execute(parameters)
            return result.to_json() if hasattr(result, "to_json") else str(result)


    class ToolRegistry:
        def __init__(self) -> None:
            self._tools: dict[str, Tool] = {}
            self._functions: dict[str, Any] = {}

        def register_tool(self, tool: Tool) -> None:
            self._tools[tool.name] = tool
            self._functions[tool.name] = getattr(tool, "run", None)

        def list_tools(self) -> list[str]:
            return list(self._tools.keys())

        def get_tools_description(self) -> str:
            return "\n".join(
                f"- {tool.name}: {getattr(tool, 'description', '').strip()}"
                for tool in self._tools.values()
            )

        def execute_tool(self, name: str, input_text: str) -> str:
            tool = self._tools.get(name)
            if tool is None:
                return json.dumps(
                    {
                        "status": "error",
                        "text": f"Tool '{name}' is not registered.",
                        "available_tools": self.list_tools(),
                    },
                    ensure_ascii=False,
                )

            parameters = tool.get_parameters() if hasattr(tool, "get_parameters") else []
            payload_key = parameters[0].name if parameters else "input"
            payload = {payload_key: input_text}
            result = tool.run(payload) if hasattr(tool, "run") else tool.execute(payload)
            return result if isinstance(result, str) else str(result)


    class HelloAgentsLLM:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

        def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
            raise RuntimeError(
                "hello_agents is not installed in the current environment. "
                "Install project dependencies before invoking the runtime LLM client."
            )
