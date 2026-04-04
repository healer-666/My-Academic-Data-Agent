"""OpenAI-compatible embedding client."""

from __future__ import annotations

from typing import Iterable

class OpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        model_id: str,
        api_key: str,
        base_url: str,
        timeout: int = 120,
    ) -> None:
        self.model_id = str(model_id or "").strip()
        self.api_key = str(api_key or "").strip()
        self.base_url = str(base_url or "").strip()
        self.timeout = int(timeout)
        try:
            from openai import OpenAI
        except Exception as exc:
            raise RuntimeError(f"openai package is unavailable: {exc}") from exc
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        normalized = [str(text or "").strip() for text in texts if str(text or "").strip()]
        if not normalized:
            return []
        response = self._client.embeddings.create(
            model=self.model_id,
            input=normalized,
        )
        return [list(item.embedding) for item in response.data]
