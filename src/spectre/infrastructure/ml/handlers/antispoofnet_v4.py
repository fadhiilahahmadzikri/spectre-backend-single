from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from spectre.config import Settings
from spectre.core.logger import get_logger
from spectre.infrastructure.ml.handlers.base import BaseFASHandler, FASInferenceResult
from spectre.infrastructure.ml.image_preprocessor import ImagePreprocessor
from spectre.infrastructure.ml.model_registry import ModelRegistry

logger = get_logger(__name__)

_MODEL_ID = "antispoofnet_v4"
_VERSION = "1.0"


class AntiSpoofNetV4Handler(BaseFASHandler):
    def __init__(
        self,
        settings: Settings,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        self._settings = settings
        self._registry = model_registry if model_registry is not None else ModelRegistry()
        self._preprocessor = ImagePreprocessor(settings)

    @property
    def model_id(self) -> str:
        return _MODEL_ID

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def is_loaded(self) -> bool:
        return self._registry.is_loaded

    @property
    def supports_tta(self) -> bool:
        return True

    @property
    def underlying_model_registry(self) -> ModelRegistry:
        return self._registry

    def load(self, artifact_path: Path) -> None:
        if not self._registry.is_loaded:
            self._registry.load(self._settings)
        dummy = np.zeros(
            (self._settings.model_img_size, self._settings.model_img_size, 3),
            dtype=np.float32,
        )
        self._registry.classify(dummy)
        logger.info(
            "fas_handler_loaded | model_id={} | version={}",
            self.model_id,
            self.version,
        )

    def preprocess(self, image_bytes: bytes) -> np.ndarray:
        return self._preprocessor.preprocess(image_bytes)

    def predict(self, preprocessed: np.ndarray) -> np.ndarray:
        return self._registry.classify(preprocessed)

    def postprocess(self, raw_output: np.ndarray) -> list[float]:
        probs = raw_output
        if probs.ndim == 2:
            probs = probs[0]
        return probs.tolist()

    def infer_tta(self, image_bytes: bytes) -> FASInferenceResult:
        start = time.monotonic()
        batch, weights = self._preprocessor.build_tta_batch(image_bytes)
        all_probs = self._registry.classify(batch)
        probs = np.average(all_probs, axis=0, weights=np.array(weights))
        elapsed_ms = int((time.monotonic() - start) * 1000)
        result = FASInferenceResult(
            probabilities=probs.tolist(),
            inference_time_ms=elapsed_ms,
            model_id=self.model_id,
            model_version=self.version,
        )
        logger.info(
            "fas_inference | model_id={} | version={} | latency_ms={} | mode=tta | top_class={} | confidence={}",
            self.model_id,
            self.version,
            elapsed_ms,
            int(np.argmax(probs)),
            round(float(np.max(probs)), 4),
        )
        return result
