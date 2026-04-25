"""LLM construction helpers."""

from __future__ import annotations

from typing import Any

from .compat import HelloAgentsLLM

from .config import RuntimeConfig


class ConfiguredLLM:
    """Small adapter that applies project-wide default invoke options."""

    def __init__(self, llm: HelloAgentsLLM, default_invoke_kwargs: dict[str, Any] | None = None):
        self._llm = llm
        self.default_invoke_kwargs = dict(default_invoke_kwargs or {})

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        invoke_kwargs = {**self.default_invoke_kwargs, **kwargs}
        return self._llm.invoke(messages, **invoke_kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)


def _default_invoke_kwargs(config: RuntimeConfig) -> dict[str, Any]:
    if config.deepseek_flash_configured:
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {}


def build_llm(config: RuntimeConfig) -> ConfiguredLLM:
    """Construct the hello-agents LLM client from validated config."""

    llm = HelloAgentsLLM(
        model=config.model_id,
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout,
    )
    return ConfiguredLLM(llm, _default_invoke_kwargs(config))
