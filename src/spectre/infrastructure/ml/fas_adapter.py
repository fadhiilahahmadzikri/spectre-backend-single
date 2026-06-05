from __future__ import annotations

from spectre.config import Settings
from spectre.core.logger import get_logger
from spectre.domain.exceptions.face_exceptions import ModelInferenceError, ModelNotLoadedError
from spectre.domain.ports.ml_ports import AbstractFASModel
from spectre.domain.value_objects.liveness_result import LivenessResult
from spectre.infrastructure.ml.fas_model_registry import FASModelRegistry

logger = get_logger(__name__)


class KerasFASAdapter(AbstractFASModel):

    def __init__(self, registry: FASModelRegistry, settings: Settings) -> None:
        self._registry = registry
        self._settings = settings
        self._last_active_id: str | None = None

    def _resolve_active(self):
        active_id = self._settings.active_fas_model
        if active_id != self._last_active_id and self._last_active_id is not None:
            logger.info(
                "fas_active_model_changed | from={} | to={}",
                self._last_active_id,
                active_id,
            )
        self._last_active_id = active_id
        handler = self._registry.get(active_id)
        return active_id, handler

    def predict(self, image_bytes: bytes, *, threshold: float = 0.5) -> LivenessResult:
        try:
            active_id, handler = self._resolve_active()
        except ModelNotLoadedError:
            raise
        try:
            result = handler.infer(image_bytes)
            return LivenessResult.from_probabilities(
                probabilities=result.probabilities,
                threshold=threshold,
                inference_time_ms=result.inference_time_ms,
            )
        except Exception as exc:
            raise ModelInferenceError(
                f"FAS inference failed for model '{active_id}': {exc}"
            ) from exc

    def predict_batch(self, image_bytes: bytes, *, threshold: float = 0.5) -> LivenessResult:
        try:
            active_id, handler = self._resolve_active()
        except ModelNotLoadedError:
            raise
        try:
            if handler.supports_tta:
                result = handler.infer_tta(image_bytes)
            else:
                logger.debug(
                    "fas_tta_fallback | model_id={} | reason=not_supported",
                    active_id,
                )
                result = handler.infer(image_bytes)
            return LivenessResult.from_probabilities(
                probabilities=result.probabilities,
                threshold=threshold,
                inference_time_ms=result.inference_time_ms,
            )
        except Exception as exc:
            raise ModelInferenceError(
                f"FAS batch inference failed for model '{active_id}': {exc}"
            ) from exc
