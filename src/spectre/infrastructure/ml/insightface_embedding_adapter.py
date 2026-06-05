from __future__ import annotations

import numpy as np

from spectre.domain.exceptions.face_exceptions import ModelInferenceError, NoFaceDetectedError
from spectre.domain.ports.ml_ports import AbstractEmbeddingModel
from spectre.domain.value_objects.face_embedding import FaceEmbedding
from spectre.infrastructure.ml.insightface_registry import InsightFaceRegistry


class InsightFaceEmbeddingAdapter(AbstractEmbeddingModel):

    def __init__(self, registry: InsightFaceRegistry) -> None:
        self._registry = registry

    def extract(self, image: np.ndarray) -> FaceEmbedding:
        raise NotImplementedError("Use extract_from_bytes() for InsightFace pipeline.")

    def extract_from_bytes(self, image_bytes: bytes) -> FaceEmbedding:
        try:
            raw = self._registry.extract_embedding(image_bytes)
            return FaceEmbedding.from_list(raw.tolist())
        except ValueError as exc:
            if "No face detected" in str(exc):
                raise NoFaceDetectedError() from exc
            raise ModelInferenceError(f"InsightFace embedding extraction failed: {exc}") from exc
        except Exception as exc:
            raise ModelInferenceError(f"InsightFace embedding extraction failed: {exc}") from exc
