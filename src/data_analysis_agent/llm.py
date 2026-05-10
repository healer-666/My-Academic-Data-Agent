"""LLM construction helpers."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from .compat import HelloAgentsLLM

from .config import RuntimeConfig


class ConfiguredLLM:
    """Small adapter that applies project-wide default invoke options."""

    def __init__(self, llm: Any, default_invoke_kwargs: dict[str, Any] | None = None):
        self._llm = llm
        self.default_invoke_kwargs = dict(default_invoke_kwargs or {})

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        invoke_kwargs = {**self.default_invoke_kwargs, **kwargs}
        return self._llm.invoke(messages, **invoke_kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)


class AnthropicMessagesLLM:
    """Minimal Anthropic Messages compatible client for MiMo/token-plan endpoints."""

    def __init__(self, *, model: str, api_key: str, base_url: str, timeout: int) -> None:
        self.model = str(model or "").strip()
        self.api_key = str(api_key or "").strip()
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.timeout = int(timeout)

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        system_prompt, anthropic_messages = self._convert_messages(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": int(kwargs.pop("max_tokens", 8192)),
            "messages": anthropic_messages,
        }
        if system_prompt:
            payload["system"] = system_prompt
        payload.update(kwargs)

        req = request.Request(
            self._messages_endpoint(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic-compatible LLM request failed: HTTP {exc.code} {detail}") from exc
        return self._extract_text(data)

    def _messages_endpoint(self) -> str:
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/messages"
        return f"{self.base_url}/v1/messages"

    @staticmethod
    def _convert_messages(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        system_parts: list[str] = []
        converted: list[dict[str, str]] = []
        for message in messages:
            role = str(message.get("role", "") or "").strip().lower()
            content = str(message.get("content", "") or "")
            if role == "system":
                if content:
                    system_parts.append(content)
                continue
            converted.append(
                {
                    "role": "assistant" if role == "assistant" else "user",
                    "content": content,
                }
            )
        if not converted:
            converted.append({"role": "user", "content": ""})
        return "\n\n".join(system_parts).strip(), converted

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        content = data.get("content", "")
        if isinstance(content, list):
            parts = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type", "text") == "text"
            ]
            return "".join(parts).strip()
        if isinstance(content, str):
            return content.strip()
        return str(data).strip()


def _default_invoke_kwargs(config: RuntimeConfig) -> dict[str, Any]:
    if config.deepseek_flash_configured:
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    if config.anthropic_messages_configured:
        return {"thinking": {"type": "disabled"}}
    return {}


def build_llm(config: RuntimeConfig) -> ConfiguredLLM:
    """Construct the hello-agents LLM client from validated config."""

    if config.anthropic_messages_configured:
        llm = AnthropicMessagesLLM(
            model=config.model_id,
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )
    else:
        llm = HelloAgentsLLM(
            model=config.model_id,
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )
    return ConfiguredLLM(llm, _default_invoke_kwargs(config))
