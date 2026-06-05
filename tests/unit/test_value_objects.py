"""Unit tests for domain value objects."""

from __future__ import annotations

import math

import pytest

from spectre.domain.value_objects.face_embedding import FaceEmbedding
from spectre.domain.value_objects.liveness_result import FAS_CLASSES, LivenessResult


class TestFaceEmbedding:
    def test_creation_valid(self):
        vec = tuple([0.1] * 512)
        emb = FaceEmbedding(vector=vec)
        assert len(emb.vector) == 512

    def test_creation_wrong_dim_raises(self):
        with pytest.raises(ValueError, match="512-dim"):
            FaceEmbedding(vector=tuple([0.1] * 256))

    def test_cosine_similarity_identical(self):
        vec = tuple([1.0] * 512)
        a = FaceEmbedding(vector=vec)
        b = FaceEmbedding(vector=vec)
        assert abs(a.cosine_similarity(b) - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        a_vec = [1.0] + [0.0] * 511
        b_vec = [0.0, 1.0] + [0.0] * 510
        a = FaceEmbedding(vector=tuple(a_vec))
        b = FaceEmbedding(vector=tuple(b_vec))
        assert abs(a.cosine_similarity(b)) < 1e-6

    def test_bytes_roundtrip(self):
        vec = tuple(float(i) / 512 for i in range(512))
        emb = FaceEmbedding(vector=vec)
        data = emb.to_bytes()
        restored = FaceEmbedding.from_bytes(data)
        for a, b in zip(emb.vector, restored.vector):
            assert abs(a - b) < 1e-6

    def test_l2_normalize(self):
        vec = tuple([3.0] * 512)
        emb = FaceEmbedding(vector=vec)
        normed = emb.l2_normalize()
        norm = math.sqrt(sum(v * v for v in normed.vector))
        assert abs(norm - 1.0) < 1e-5


class TestLivenessResult:
    def test_from_probabilities_real(self):
        probs = [0.01, 0.01, 0.01, 0.01, 0.01, 0.95]
        result = LivenessResult.from_probabilities(probs, threshold=0.5)
        assert result.is_live
        assert result.predicted_class == "realperson"
        assert result.confidence == 0.95

    def test_from_probabilities_spoof(self):
        probs = [0.05, 0.05, 0.05, 0.05, 0.75, 0.05]
        result = LivenessResult.from_probabilities(probs, threshold=0.5)
        assert not result.is_live
        assert result.predicted_class == "fake_screen"

    def test_live_probability(self):
        probs = [0.1, 0.1, 0.1, 0.1, 0.1, 0.5]
        result = LivenessResult.from_probabilities(probs)
        assert result.live_probability == 0.5
        assert abs(result.spoof_probability - 0.5) < 1e-6

    def test_class_count(self):
        assert len(FAS_CLASSES) == 6
        assert FAS_CLASSES[5] == "realperson"
