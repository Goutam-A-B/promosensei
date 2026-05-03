"""Deterministic hashing-trick embedding provider.

This is *not* a high-quality semantic model — it's the hashing trick from
Weinberger et al. (2009) applied to character n-grams plus word tokens. The
goal is to give Phase 2 a **dependency-free default** that:

- runs in tests without PyTorch / network
- is deterministic across processes (so vectors are stable across restarts)
- still places lexically-similar queries near matching products, which is
  enough to validate the rest of the pipeline (query parser, ranker, API).

For real semantic intelligence in production, swap to
`SentenceTransformersProvider` or `OpenAIEmbeddingProvider`.
"""
from __future__ import annotations

import hashlib
import re

from app.embeddings.similarity import l2_normalize

_TOKEN = re.compile(r"[a-z0-9₹]+", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    text = (text or "").lower()
    words = _TOKEN.findall(text)
    grams: list[str] = list(words)
    # Character 3-grams of each word add some fuzzy-match resilience.
    for word in words:
        if len(word) <= 3:
            grams.append(word)
            continue
        for i in range(len(word) - 2):
            grams.append(word[i : i + 3])
    return grams


def _hash_index(token: str, dim: int) -> tuple[int, int]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    idx = int.from_bytes(digest[:4], "big") % dim
    sign = 1 if (digest[4] & 1) == 0 else -1
    return idx, sign


class HashingEmbeddingProvider:
    def __init__(self, dim: int = 256, model_id: str = "hashing-v1") -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim
        self._model_id = f"hashing:{model_id}:{dim}"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        toks = _tokens(text)
        if not toks:
            return vec
        for tok in toks:
            idx, sign = _hash_index(tok, self._dim)
            vec[idx] += sign
        return l2_normalize(vec)
