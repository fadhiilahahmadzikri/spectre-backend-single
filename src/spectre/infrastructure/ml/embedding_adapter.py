"""Embedding model adapter — implements AbstractEmbeddingModel using the ModelRegistry."""

from __future__ import annotations

import numpy as np

from spectre.domain.exceptions.face_exceptions import ModelInferenceError
from spectre.domain.ports.ml_ports import AbstractEmbeddingModel
from spectre.domain.value_objects.face_embedding import FaceEmbedding
from spectre.infrastructure.ml.model_registry import ModelRegistry


class KerasEmbeddingAdapter(AbstractEmbeddingModel):
    """Adapts the ModelRegistry's embedding extraction to the domain port.

    Extracts the 512-dim vector from the fsfm_embedder layer and wraps
    it as a FaceEmbedding value object.
    """

    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry

    def extract(self, image: np.ndarray) -> FaceEmbedding:
        """Extract face embedding from a preprocessed image.

        Args:
            image: Preprocessed float32 array of shape (256, 256, 3).

        Returns:
            L2-normalized 512-dim FaceEmbedding.

        Raises:
            ModelInferenceError: If embedding extraction fails.
        """
        try:
            raw = self._registry.extract_embedding(image)
            return FaceEmbedding.from_list(raw.tolist())
        except Exception as exc:
            raise ModelInferenceError(
                f"Embedding extraction failed: {exc}"
            ) from exc
