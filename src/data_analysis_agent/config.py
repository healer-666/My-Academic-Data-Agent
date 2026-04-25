"""Runtime configuration and tokenizer compatibility helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import tiktoken
except Exception:  # pragma: no cover - dependency-light test environments
    tiktoken = None

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dependency-light test environments
    def load_dotenv(*args, **kwargs):
        return False


_TOKEN_PATCH_APPLIED = False
_SAFE_TIKTOKEN_MODEL_PREFIXES = (
    "gpt-3.5",
    "gpt-4",
    "text-embedding-3",
    "text-embedding-ada",
)

DEEPSEEK_FLASH_MODEL_ID = "deepseek-v4-flash"
DEEPSEEK_PRO_MODEL_ID = "deepseek-v4-pro"
_DEEPSEEK_LEGACY_FLASH_ALIASES = {"deepseek-chat"}
_DEEPSEEK_LEGACY_PRO_ALIASES = {"deepseek-reasoner"}


@dataclass(frozen=True)
class RuntimeConfig:
    model_id: str
    api_key: str
    base_url: str
    timeout: int = 120
    tavily_api_key: Optional[str] = None
    embedding_model_id: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_base_url: Optional[str] = None
    embedding_timeout: int = 120
    vision_model_id: Optional[str] = None
    vision_api_key: Optional[str] = None
    vision_base_url: Optional[str] = None
    vision_timeout: int = 120

    @property
    def vision_configured(self) -> bool:
        return bool(self.vision_model_id and self.vision_api_key and self.vision_base_url)

    @property
    def embedding_configured(self) -> bool:
        return bool(self.embedding_model_id and self.embedding_api_key and self.embedding_base_url)

    @property
    def deepseek_flash_configured(self) -> bool:
        return is_deepseek_base_url(self.base_url) and self.model_id == DEEPSEEK_FLASH_MODEL_ID


def is_deepseek_base_url(base_url: str | None) -> bool:
    return "api.deepseek.com" in str(base_url or "").lower()


def resolve_text_model_id(model_id: str, base_url: str) -> str:
    """Normalize DeepSeek text models to V4 Flash to avoid accidental Pro/thinking use."""

    normalized = str(model_id or "").strip()
    lower_model_id = normalized.lower()
    if not is_deepseek_base_url(base_url):
        return normalized

    if (
        lower_model_id == DEEPSEEK_FLASH_MODEL_ID
        or lower_model_id in _DEEPSEEK_LEGACY_FLASH_ALIASES
        or lower_model_id == DEEPSEEK_PRO_MODEL_ID
        or lower_model_id in _DEEPSEEK_LEGACY_PRO_ALIASES
        or lower_model_id.startswith("deepseek")
    ):
        return DEEPSEEK_FLASH_MODEL_ID

    return normalized


def _patched_get_encoding(self):
    model_name = str(getattr(self, "model", "") or "").strip().lower()

    try:
        if tiktoken is None:
            return None
        if model_name and any(model_name.startswith(prefix) for prefix in _SAFE_TIKTOKEN_MODEL_PREFIXES):
            return tiktoken.encoding_for_model(model_name)
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None


def apply_token_counter_patch():
    """Apply a generic OpenAI-compatible tokenizer fallback patch once."""

    global _TOKEN_PATCH_APPLIED
    if _TOKEN_PATCH_APPLIED:
        return _patched_get_encoding

    try:
        import hello_agents.context.token_counter
    except ModuleNotFoundError:
        _TOKEN_PATCH_APPLIED = True
        return _patched_get_encoding

    hello_agents.context.token_counter.TokenCounter._get_encoding = _patched_get_encoding
    _TOKEN_PATCH_APPLIED = True
    return _patched_get_encoding


def load_runtime_config(env_file: Optional[str | Path] = None) -> RuntimeConfig:
    """Load and validate runtime configuration from the environment."""

    if env_file is not None:
        load_dotenv(dotenv_path=env_file, override=False)
    else:
        load_dotenv(override=False)

    required_env_vars = ("LLM_MODEL_ID", "LLM_BASE_URL", "LLM_API_KEY")
    missing_env_vars = [name for name in required_env_vars if not os.getenv(name)]
    if missing_env_vars:
        raise ValueError(
            "Missing required environment variables: "
            + ", ".join(missing_env_vars)
            + ". Create a .env file from .env.example or export them before running the project."
        )

    timeout = int(os.getenv("LLM_TIMEOUT", "120"))
    embedding_timeout = int(os.getenv("EMBEDDING_TIMEOUT", str(timeout)))
    vision_timeout = int(os.getenv("VISION_LLM_TIMEOUT", str(timeout)))
    model_id = resolve_text_model_id(os.environ["LLM_MODEL_ID"], os.environ["LLM_BASE_URL"])
    config = RuntimeConfig(
        model_id=model_id,
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
        timeout=timeout,
        tavily_api_key=os.getenv("TAVILY_API_KEY"),
        embedding_model_id=os.getenv("EMBEDDING_MODEL_ID"),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY"),
        embedding_base_url=os.getenv("EMBEDDING_BASE_URL"),
        embedding_timeout=embedding_timeout,
        vision_model_id=os.getenv("VISION_LLM_MODEL_ID"),
        vision_api_key=os.getenv("VISION_LLM_API_KEY"),
        vision_base_url=os.getenv("VISION_LLM_BASE_URL"),
        vision_timeout=vision_timeout,
    )

    os.environ.setdefault("LLM_TIMEOUT", str(config.timeout))
    os.environ["LLM_MODEL_ID"] = config.model_id
    apply_token_counter_patch()
    return config
