from __future__ import annotations

from pathlib import Path

from spectre.config import Settings
from spectre.core.logger import get_logger
from spectre.domain.exceptions.face_exceptions import ModelNotLoadedError
from spectre.infrastructure.ml.fas_model_catalog import FAS_MODEL_CATALOG, FASModelSpec
from spectre.infrastructure.ml.handlers.antispoofnet_v4 import AntiSpoofNetV4Handler
from spectre.infrastructure.ml.handlers.base import BaseFASHandler
from spectre.infrastructure.ml.model_registry import ModelRegistry

logger = get_logger(__name__)


class FASModelRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, BaseFASHandler] = {}
        self._load_errors: dict[str, str] = {}

    def load_all(
        self,
        settings: Settings,
        *,
        shared_antispoofnet_registry: ModelRegistry | None = None,
    ) -> None:
        for model_id, spec in FAS_MODEL_CATALOG.items():
            try:
                handler = self._instantiate_handler(spec, settings, shared_antispoofnet_registry)
                artifact_path = self._resolve_artifact_path(settings, spec)
                handler.load(artifact_path)
                self._handlers[model_id] = handler
                self._load_errors.pop(model_id, None)
                logger.info(
                    "fas_handler_registered | model_id={} | version={}",
                    model_id,
                    spec.version,
                )
            except Exception as exc:
                err_msg = f"{type(exc).__name__}: {exc}"
                self._load_errors[model_id] = err_msg
                logger.warning(
                    "fas_handler_load_failed | model_id={} | error={}",
                    model_id,
                    err_msg,
                )
                continue

    def _instantiate_handler(
        self,
        spec: FASModelSpec,
        settings: Settings,
        shared_antispoofnet_registry: ModelRegistry | None,
    ) -> BaseFASHandler:
        if spec.handler_cls is AntiSpoofNetV4Handler:
            return AntiSpoofNetV4Handler(
                settings=settings,
                model_registry=shared_antispoofnet_registry,
            )
        return spec.handler_cls(settings=settings)

    def _resolve_artifact_path(self, settings: Settings, spec: FASModelSpec) -> Path:
        value = getattr(settings, spec.artifact_path_attr)
        return Path(value) if not isinstance(value, Path) else value

    def get(self, model_id: str) -> BaseFASHandler:
        if model_id in self._handlers:
            return self._handlers[model_id]
        raise ModelNotLoadedError(
            message=(
                f"FAS model '{model_id}' is not loaded. "
                f"Available: {sorted(self._handlers.keys())}"
            ),
            model_id=model_id,
            available=sorted(self._handlers.keys()),
            load_errors=dict(self._load_errors),
        )

    def is_valid_model_id(self, model_id: str) -> bool:
        return model_id in self._handlers

    def list_models(self) -> list[dict]:
        entries: list[dict] = []
        for model_id, spec in FAS_MODEL_CATALOG.items():
            handler = self._handlers.get(model_id)
            entries.append(
                {
                    "model_id": model_id,
                    "version": spec.version,
                    "description": spec.description,
                    "supports_tta": spec.supports_tta,
                    "is_loaded": handler is not None and handler.is_loaded,
                    "load_error": self._load_errors.get(model_id),
                }
            )
        return entries

    @property
    def loaded_count(self) -> int:
        return len(self._handlers)
