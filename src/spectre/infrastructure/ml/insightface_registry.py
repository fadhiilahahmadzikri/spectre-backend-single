from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from spectre.config import Settings
from spectre.core.logger import get_logger

logger = get_logger(__name__)

_INSTANCE: InsightFaceRegistry | None = None


class InsightFaceRegistry:

    def __init__(self) -> None:
        self._app = None
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load(self, settings: Settings) -> None:
        from insightface.app import FaceAnalysis

        model_name = settings.insightface_model_name
        model_root = settings.insightface_model_root
        det_size = settings.insightface_det_size

        logger.info(
            "insightface_loading",
            model=model_name,
            root=str(model_root) if model_root else "default",
        )
        start = time.monotonic()

        kwargs: dict = {"name": model_name, "allowed_modules": ["recognition", "detection"]}
        if model_root:
            kwargs["root"] = str(model_root)

        self._app = FaceAnalysis(**kwargs)
        self._app.prepare(ctx_id=-1, det_size=(det_size, det_size))

        elapsed = time.monotonic() - start
        logger.info("insightface_loaded", elapsed_sec=round(elapsed, 2))
        self._is_loaded = True

    def extract_embedding(self, image_bytes: bytes) -> np.ndarray:
        if self._app is None:
            raise RuntimeError("InsightFace model not loaded. Call load() first.")

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if bgr is None:
            raise ValueError("Failed to decode image bytes.")

        faces = self._app.get(bgr)

        if not faces:
            raise ValueError("No face detected in the provided image.")

        primary = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

        embedding = primary.embedding.astype(np.float32)
        norm = np.linalg.norm(embedding)
        if norm > 1e-8:
            embedding = embedding / norm

        return embedding

    def extract_embedding_multi(self, image_bytes: bytes) -> list[np.ndarray]:
        if self._app is None:
            raise RuntimeError("InsightFace model not loaded. Call load() first.")

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if bgr is None:
            raise ValueError("Failed to decode image bytes.")

        faces = self._app.get(bgr)

        if not faces:
            raise ValueError("No face detected in the provided image.")

        results = []
        for face in faces:
            emb = face.embedding.astype(np.float32)
            norm = np.linalg.norm(emb)
            if norm > 1e-8:
                emb = emb / norm
            results.append(emb)

        return results


def get_insightface_registry() -> InsightFaceRegistry:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = InsightFaceRegistry()
    return _INSTANCE
