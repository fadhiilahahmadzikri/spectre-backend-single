from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from spectre.domain.value_objects.face_embedding import FaceEmbedding
from spectre.domain.value_objects.liveness_result import LivenessResult


class AbstractFASModel(ABC):

    @abstractmethod
    def predict(self, image_bytes: bytes, *, threshold: float = 0.5) -> LivenessResult:
        ...

    @abstractmethod
    def predict_batch(self, image_bytes: bytes, *, threshold: float = 0.5) -> LivenessResult:
        ...


class AbstractEmbeddingModel(ABC):

    @abstractmethod
    def extract(self, image: np.ndarray) -> FaceEmbedding:
        ...

    def extract_from_bytes(self, image_bytes: bytes) -> FaceEmbedding:
        raise NotImplementedError
