"""OpenAI embedding provider.

Lazy-imported so that `openai` isn't a hard dependency. Default model is
`text-embedding-3-small` (1536 dims).
"""
from __future__ import annotations

import logging
import os

from app.embeddings.similarity import l2_normalize

logger = logging.getLogger(__name__)

_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
    ) -> None:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "openai is not installed. Run `pip install openai` or pick a different provider."
            ) from exc

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OpenAIEmbeddingProvider requires OPENAI_API_KEY in env or constructor."
            )

        self._client = OpenAI(api_key=key)
        self._model = model
        self._dim = _DIMS.get(model, 1536)
        self._model_id = f"openai:{model}:{self._dim}"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # OpenAI accepts batched inputs natively. The caller owns batch sizing.
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [l2_normalize(list(map(float, item.embedding))) for item in response.data]
