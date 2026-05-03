"""Build and refresh product embeddings.

The indexer is **incremental**: on every run it only embeds products that are
either new (no row in `product_embeddings` for the active model) or stale
(title hash changed since the last embedding). Previous-model vectors are
left untouched so we can roll forward / backward safely (edge case 5.2).
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.factory import get_embedding_provider
from app.models import Product, ProductEmbedding

logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    model_id: str
    embedded: int = 0
    skipped: int = 0
    refreshed: int = 0


def title_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().lower().encode("utf-8")).hexdigest()[:32]


def embed_text_for(product: Product) -> str:
    """The text we feed into the embedding model.

    Phase 3 mixes brand into the embed text so two near-identical titles for
    different brands don't collapse into the same vector neighborhood. We
    intentionally leave the model number out — it's matched as a hard signal
    by the matcher, and including it dilutes the semantic intent.
    """
    parts = [product.canonical_title or ""]
    if product.brand:
        parts.append(product.brand)
    return " ".join(p for p in parts if p).strip()


def _chunked(seq: list, size: int) -> Iterable[list]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def reindex_products(
    db: Session,
    *,
    provider: EmbeddingProvider | None = None,
    batch_size: int | None = None,
    limit: int | None = None,
) -> IndexStats:
    settings = get_settings()
    provider = provider or get_embedding_provider()
    batch_size = batch_size or settings.embedding_batch_size
    stats = IndexStats(model_id=provider.model_id)

    # Find existing embeddings for this model so we know what's already done.
    existing = {
        row.product_id: row
        for row in db.scalars(
            select(ProductEmbedding).where(ProductEmbedding.model_id == provider.model_id)
        ).all()
    }

    products = db.scalars(select(Product)).all()
    if limit is not None:
        products = products[:limit]

    queue: list[Product] = []
    for product in products:
        text = embed_text_for(product)
        h = title_hash(text)
        # Keep the product's own title_hash up to date — handy for downstream debugging
        # and for cheap "did the source text actually change?" checks elsewhere.
        if product.title_hash != h:
            product.title_hash = h

        existing_row = existing.get(product.id)
        if existing_row is None:
            queue.append(product)
        elif existing_row.title_hash != h:
            queue.append(product)
        else:
            stats.skipped += 1

    if not queue:
        db.commit()
        logger.info(
            "Indexer: nothing to do for %s (skipped=%d)", provider.model_id, stats.skipped
        )
        return stats

    logger.info("Indexer: embedding %d products with %s", len(queue), provider.model_id)

    for batch in _chunked(queue, batch_size):
        texts = [embed_text_for(p) for p in batch]
        vectors = provider.embed(texts)
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"Provider returned {len(vectors)} vectors for {len(batch)} inputs"
            )
        for product, vector in zip(batch, vectors):
            text = embed_text_for(product)
            h = title_hash(text)
            payload = json.dumps(vector)
            row = existing.get(product.id)
            if row is None:
                row = ProductEmbedding(
                    product_id=product.id,
                    model_id=provider.model_id,
                    dim=provider.dim,
                    vector_json=payload,
                    title_hash=h,
                )
                db.add(row)
                existing[product.id] = row
                stats.embedded += 1
            else:
                row.vector_json = payload
                row.dim = provider.dim
                row.title_hash = h
                stats.refreshed += 1

    db.commit()
    logger.info(
        "Indexer done: model=%s embedded=%d refreshed=%d skipped=%d",
        provider.model_id,
        stats.embedded,
        stats.refreshed,
        stats.skipped,
    )
    return stats
