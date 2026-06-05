"""FaceEmbedding value object — 512-dim float vector with similarity computation."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class FaceEmbedding:
    """Immutable 512-dimensional face embedding vector.

    Extracted from the fsfm_embedder layer of AntiSpoofNetV4.
    Provides cosine similarity computation for face matching.
    """

    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.vector) != 512:
            raise ValueError(f"Embedding must be 512-dim, got {len(self.vector)}")

    @classmethod
    def from_list(cls, values: list[float]) -> FaceEmbedding:
        """Create from a list of floats."""
        return cls(vector=tuple(values))

    @classmethod
    def from_bytes(cls, data: bytes) -> FaceEmbedding:
        """Deserialize from raw bytes (4 bytes per float32, little-endian)."""
        import struct

        n_floats = len(data) // 4
        values = struct.unpack(f"<{n_floats}f", data)
        return cls(vector=values)

    def to_bytes(self) -> bytes:
        """Serialize to raw bytes (4 bytes per float32, little-endian)."""
        import struct

        return struct.pack(f"<{len(self.vector)}f", *self.vector)

    def cosine_similarity(self, other: FaceEmbedding) -> float:
        """Compute cosine similarity between this embedding and another.

        Returns:
            Cosine similarity in range [-1.0, 1.0]. Higher means more similar.
        """
        dot = sum(a * b for a, b in zip(self.vector, other.vector))
        norm_a = math.sqrt(sum(a * a for a in self.vector))
        norm_b = math.sqrt(sum(b * b for b in other.vector))

        if norm_a < 1e-8 or norm_b < 1e-8:
            return 0.0

        return dot / (norm_a * norm_b)

    def l2_normalize(self) -> FaceEmbedding:
        """Return L2-normalized copy of this embedding."""
        norm = math.sqrt(sum(v * v for v in self.vector))
        if norm < 1e-8:
            return self
        return FaceEmbedding(vector=tuple(v / norm for v in self.vector))
