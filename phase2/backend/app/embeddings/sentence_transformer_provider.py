"""Local sentence-transformers embedding provider.

`sentence-transformers` and its torch dependency are heavy (~300 MB), so this
module imports them lazily. The provider is only loaded if
`EMBEDDING_PROVIDER=sentence-transformers` is set.

Default model: `sentence-transformers/all-MiniLM-L6-v2` — 384 dims, fast,
works offline once cached, and produces strong cosine similarities for short
product titles. For Hinglish / multilingual queries (edge case 4.3), switch
to `paraphrase-multilingual-MiniLM-L12-v2`.
"""
from __future__ import annotations

import logging

from app.embeddings.similarity import l2_normalize

logger = logging.getLogger(__name__)


class SentenceTransformersProvider:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers is not installed. Run "
                "`pip install sentence-transformers` or set EMBEDDING_PROVIDER=hashing."
            ) from exc

        logger.info("Loading sentence-transformers model %s", model_name)
        self._model = SentenceTransformer(model_name)
        self._dim = int(self._model.get_sentence_embedding_dimension())
        # Slashes in model ids would confuse our model_id format — replace them.
        safe_name = model_name.replace("/", "_")
        self._model_id = f"st:{safe_name}:{self._dim}"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # convert_to_numpy=True returns a 2D array we then convert to lists.
        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [l2_normalize(list(map(float, v))) for v in vectors]
