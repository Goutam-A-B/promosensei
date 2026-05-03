"""Tests for the hashing-trick embedding provider and similarity helpers.

We focus on the dependency-free hashing provider — it's the one that
actually runs in CI. Sentence-transformers and OpenAI providers are smoke
tested manually before a release.
"""
from __future__ import annotations

import math

from app.embeddings.hashing import HashingEmbeddingProvider
from app.embeddings.similarity import cosine_similarity, l2_normalize


class TestHashingProvider:
    def test_dim_and_model_id_format(self):
        provider = HashingEmbeddingProvider(dim=128, model_id="hashing-v1")
        assert provider.dim == 128
        assert provider.model_id == "hashing:hashing-v1:128"

    def test_vectors_are_normalized(self):
        provider = HashingEmbeddingProvider(dim=64)
        [vec] = provider.embed(["wireless earbuds"])
        norm = math.sqrt(sum(v * v for v in vec))
        assert math.isclose(norm, 1.0, rel_tol=1e-6)

    def test_deterministic_across_calls(self):
        provider = HashingEmbeddingProvider(dim=64)
        a = provider.embed(["sony headphones"])[0]
        b = provider.embed(["sony headphones"])[0]
        assert a == b

    def test_deterministic_across_instances(self):
        """Stability across restarts — vectors persisted in DB stay valid."""
        a = HashingEmbeddingProvider(dim=64).embed(["sony headphones"])[0]
        b = HashingEmbeddingProvider(dim=64).embed(["sony headphones"])[0]
        assert a == b

    def test_empty_text_yields_zero_vector(self):
        provider = HashingEmbeddingProvider(dim=32)
        [vec] = provider.embed([""])
        assert vec == [0.0] * 32

    def test_similar_text_has_higher_similarity_than_unrelated(self):
        provider = HashingEmbeddingProvider(dim=512)
        query = provider.embed(["wireless bluetooth earbuds"])[0]
        relevant = provider.embed(["boAt Airdopes Bluetooth Earbuds"])[0]
        unrelated = provider.embed(["Apple iPhone 15 Pro"])[0]
        sim_relevant = cosine_similarity(query, relevant)
        sim_unrelated = cosine_similarity(query, unrelated)
        assert sim_relevant > sim_unrelated


class TestSimilarity:
    def test_l2_normalize_unit_norm(self):
        vec = l2_normalize([3.0, 4.0])
        assert math.isclose(vec[0], 0.6, rel_tol=1e-9)
        assert math.isclose(vec[1], 0.8, rel_tol=1e-9)

    def test_l2_normalize_zero_vector(self):
        # Zero vector stays zero — never divide by zero.
        assert l2_normalize([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]

    def test_cosine_identical_vectors(self):
        assert math.isclose(cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0)

    def test_cosine_orthogonal_vectors(self):
        assert math.isclose(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_cosine_opposite_vectors(self):
        assert math.isclose(cosine_similarity([1.0, 0.0], [-1.0, 0.0]), -1.0)

    def test_cosine_zero_vector_is_zero(self):
        # We don't want a NaN escaping into the ranker.
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_cosine_dim_mismatch_raises(self):
        import pytest

        with pytest.raises(ValueError):
            cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])
