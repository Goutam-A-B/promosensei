"""Provider factory cached per-process.

Heavy providers (sentence-transformers) only load when first requested.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.hashing import HashingEmbeddingProvider


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    name = (settings.embedding_provider or "hashing").lower()

    if name in {"hashing", "hash", "test"}:
        return HashingEmbeddingProvider(
            dim=settings.embedding_dim,
            model_id=settings.embedding_model or "hashing-v1",
        )

    if name in {"sentence-transformers", "st", "sentence_transformers"}:
        from app.embeddings.sentence_transformer_provider import SentenceTransformersProvider

        return SentenceTransformersProvider(
            model_name=settings.embedding_model
            if settings.embedding_model and "/" in settings.embedding_model
            else "sentence-transformers/all-MiniLM-L6-v2"
        )

    if name in {"openai"}:
        from app.embeddings.openai_provider import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )

    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER={settings.embedding_provider!r}. "
        "Use 'hashing', 'sentence-transformers', or 'openai'."
    )


def reset_provider_cache() -> None:
    """Test helper — drop the cached provider so a new settings instance is picked up."""
    get_embedding_provider.cache_clear()
