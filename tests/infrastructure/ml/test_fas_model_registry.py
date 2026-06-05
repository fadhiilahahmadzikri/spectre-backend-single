from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from spectre.config import Settings
from spectre.domain.exceptions.face_exceptions import ModelNotLoadedError
from spectre.infrastructure.ml.fas_model_catalog import FASModelSpec
from spectre.infrastructure.ml.handlers.base import BaseFASHandler


class _FakeHandler(BaseFASHandler):
    def __init__(self, settings: Settings, **kwargs) -> None:
        self._loaded = False
        self._mid = kwargs.get("model_id_override", "fake_handler")
        self._ver = kwargs.get("version_override", "0.0.1")
        self._should_fail = kwargs.get("should_fail", False)

    @property
    def model_id(self) -> str:
        return self._mid

    @property
    def version(self) -> str:
        return self._ver

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self, artifact_path: Path) -> None:
        if self._should_fail:
            raise RuntimeError("simulated load failure")
        self._loaded = True

    def preprocess(self, image_bytes: bytes) -> np.ndarray:
        return np.zeros((1,), dtype=np.float32)

    def predict(self, preprocessed: np.ndarray) -> np.ndarray:
        return np.array([[0.0] * 6], dtype=np.float32)

    def postprocess(self, raw_output: np.ndarray) -> list[float]:
        return [0.0] * 6


class _FakeHealthy(_FakeHandler):
    def __init__(self, settings: Settings, **kwargs) -> None:
        super().__init__(settings, model_id_override="model_a", version_override="1.0")


class _FakeBroken(_FakeHandler):
    def __init__(self, settings: Settings, **kwargs) -> None:
        super().__init__(
            settings,
            model_id_override="model_b",
            version_override="2.0",
            should_fail=True,
        )


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        jwt_secret_key="test_jwt_secret_64_chars_long_enough_for_hmac_hs256_signing_key",
        encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTE=",
    )


@pytest.fixture
def fake_catalog():
    return {
        "model_a": FASModelSpec(
            model_id="model_a",
            handler_cls=_FakeHealthy,
            artifact_path_attr="model_path_resolved",
            version="1.0",
            description="Healthy fake model",
            supports_tta=False,
        ),
        "model_b": FASModelSpec(
            model_id="model_b",
            handler_cls=_FakeBroken,
            artifact_path_attr="model_path_resolved",
            version="2.0",
            description="Broken fake model",
            supports_tta=False,
        ),
    }


class TestFASModelRegistry:
    def test_load_all_loads_healthy_skips_broken(
        self, test_settings: Settings, fake_catalog
    ) -> None:
        with patch(
            "spectre.infrastructure.ml.fas_model_registry.FAS_MODEL_CATALOG",
            fake_catalog,
        ):
            from spectre.infrastructure.ml.fas_model_registry import FASModelRegistry

            registry = FASModelRegistry()
            registry.load_all(test_settings)

            assert registry.is_valid_model_id("model_a") is True
            assert registry.is_valid_model_id("model_b") is False
            assert registry.loaded_count == 1

    def test_list_models_reports_both_loaded_and_failed(
        self, test_settings: Settings, fake_catalog
    ) -> None:
        with patch(
            "spectre.infrastructure.ml.fas_model_registry.FAS_MODEL_CATALOG",
            fake_catalog,
        ):
            from spectre.infrastructure.ml.fas_model_registry import FASModelRegistry

            registry = FASModelRegistry()
            registry.load_all(test_settings)

            entries = registry.list_models()
            assert len(entries) == 2

            by_id = {e["model_id"]: e for e in entries}
            assert by_id["model_a"]["is_loaded"] is True
            assert by_id["model_a"]["load_error"] is None
            assert by_id["model_a"]["version"] == "1.0"
            assert by_id["model_a"]["supports_tta"] is False

            assert by_id["model_b"]["is_loaded"] is False
            assert by_id["model_b"]["load_error"] is not None
            assert "simulated load failure" in by_id["model_b"]["load_error"]

    def test_get_returns_loaded_handler(
        self, test_settings: Settings, fake_catalog
    ) -> None:
        with patch(
            "spectre.infrastructure.ml.fas_model_registry.FAS_MODEL_CATALOG",
            fake_catalog,
        ):
            from spectre.infrastructure.ml.fas_model_registry import FASModelRegistry

            registry = FASModelRegistry()
            registry.load_all(test_settings)

            handler = registry.get("model_a")
            assert handler.model_id == "model_a"
            assert handler.is_loaded is True

    def test_get_failed_model_raises_model_not_loaded(
        self, test_settings: Settings, fake_catalog
    ) -> None:
        with patch(
            "spectre.infrastructure.ml.fas_model_registry.FAS_MODEL_CATALOG",
            fake_catalog,
        ):
            from spectre.infrastructure.ml.fas_model_registry import FASModelRegistry

            registry = FASModelRegistry()
            registry.load_all(test_settings)

            with pytest.raises(ModelNotLoadedError) as exc_info:
                registry.get("model_b")
            assert "model_b" in str(exc_info.value)

    def test_get_unknown_model_raises_model_not_loaded(
        self, test_settings: Settings, fake_catalog
    ) -> None:
        with patch(
            "spectre.infrastructure.ml.fas_model_registry.FAS_MODEL_CATALOG",
            fake_catalog,
        ):
            from spectre.infrastructure.ml.fas_model_registry import FASModelRegistry

            registry = FASModelRegistry()
            registry.load_all(test_settings)

            with pytest.raises(ModelNotLoadedError):
                registry.get("nonexistent_model_xyz")

    def test_catalog_contains_both_real_models(self) -> None:
        from spectre.infrastructure.ml.fas_model_catalog import FAS_MODEL_CATALOG

        assert "antispoofnet_v4" in FAS_MODEL_CATALOG
        assert "ilhamcaesar_resnet50" in FAS_MODEL_CATALOG
        antispoof = FAS_MODEL_CATALOG["antispoofnet_v4"]
        assert antispoof.supports_tta is True
        assert antispoof.artifact_path_attr == "model_path_resolved"
        ilham = FAS_MODEL_CATALOG["ilhamcaesar_resnet50"]
        assert ilham.supports_tta is False
        assert ilham.artifact_path_attr == "ilhamcaesar_model_path_resolved"
