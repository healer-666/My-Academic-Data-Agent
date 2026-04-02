"""Model capability registry for text and vision execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .config import RuntimeConfig
from .runtime_models import ModelCapability


@dataclass(frozen=True)
class ModelRegistry:
    runtime_config: RuntimeConfig
    text: ModelCapability
    vision: ModelCapability

    @classmethod
    def from_runtime_config(cls, runtime_config: RuntimeConfig) -> "ModelRegistry":
        return cls(
            runtime_config=runtime_config,
            text=ModelCapability(
                role="analyst_text",
                model_id=runtime_config.model_id,
                base_url=runtime_config.base_url,
                timeout=runtime_config.timeout,
                configured=bool(runtime_config.model_id and runtime_config.api_key and runtime_config.base_url),
            ),
            vision=ModelCapability(
                role="review_vision",
                model_id=runtime_config.vision_model_id or "",
                base_url=runtime_config.vision_base_url or "",
                timeout=runtime_config.vision_timeout,
                configured=runtime_config.vision_configured,
            ),
        )

    def build_text_llm(self, builder: Callable[[RuntimeConfig], Any]) -> Any:
        return builder(self.runtime_config)
