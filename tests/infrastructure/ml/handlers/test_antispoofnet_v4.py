from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from spectre.config import Settings


_ARTIFACT_PATH = Path("artifact/best_model.keras")


def _make_synthetic_jpeg_bytes(size: int = 256, seed: int = 1234) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, size=(size, size, 3), dtype=np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


@pytest.fixture(scope="module")
def test_settings() -> Settings:
    return Settings(
        jwt_secret_key="test_jwt_secret_64_chars_long_enough_for_hmac_hs256_signing_key",
        encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTE=",
        model_path=str(_ARTIFACT_PATH),
    )


@pytest.fixture(scope="module")
def loaded_registry(test_settings: Settings):
    if not _ARTIFACT_PATH.exists():
        pytest.skip(f"AntiSpoofNetV4 artifact missing at {_ARTIFACT_PATH}")
    from spectre.infrastructure.ml.model_registry import ModelRegistry

    reg = ModelRegistry()
    reg.load(test_settings)
    return reg


@pytest.fixture(scope="module")
def sample_image_bytes() -> bytes:
    return _make_synthetic_jpeg_bytes(size=256, seed=1234)


class TestAntiSpoofNetV4Handler:
    def test_handler_metadata(self, test_settings: Settings, loaded_registry) -> None:
        from spectre.infrastructure.ml.handlers.antispoofnet_v4 import AntiSpoofNetV4Handler

        handler = AntiSpoofNetV4Handler(test_settings, model_registry=loaded_registry)
        handler.load(Path(test_settings.model_path))
        assert handler.model_id == "antispoofnet_v4"
        assert handler.version == "1.0"
        assert handler.supports_tta is True
        assert handler.is_loaded is True
        assert handler.underlying_model_registry is loaded_registry

    def test_single_pass_matches_old_pipeline(
        self, test_settings: Settings, loaded_registry, sample_image_bytes: bytes
    ) -> None:
        from spectre.infrastructure.ml.handlers.antispoofnet_v4 import AntiSpoofNetV4Handler
        from spectre.infrastructure.ml.image_preprocessor import ImagePreprocessor

        preprocessor = ImagePreprocessor(test_settings)
        preprocessed = preprocessor.preprocess(sample_image_bytes)
        old_probs_raw = loaded_registry.classify(preprocessed)
        if old_probs_raw.ndim == 2:
            old_probs_raw = old_probs_raw[0]
        old_probs = old_probs_raw.astype(np.float64)

        handler = AntiSpoofNetV4Handler(test_settings, model_registry=loaded_registry)
        handler.load(Path(test_settings.model_path))
        new_result = handler.infer(sample_image_bytes)
        new_probs = np.array(new_result.probabilities, dtype=np.float64)

        assert np.allclose(old_probs, new_probs, atol=1e-6), (
            f"Single-pass divergence detected. old={old_probs.tolist()} new={new_probs.tolist()}"
        )
        assert len(new_result.probabilities) == 6
        assert new_result.model_id == "antispoofnet_v4"
        assert new_result.model_version == "1.0"

    def test_tta_matches_old_pipeline(
        self, test_settings: Settings, loaded_registry, sample_image_bytes: bytes
    ) -> None:
        from spectre.infrastructure.ml.handlers.antispoofnet_v4 import AntiSpoofNetV4Handler
        from spectre.infrastructure.ml.image_preprocessor import ImagePreprocessor

        preprocessor = ImagePreprocessor(test_settings)
        batch, weights = preprocessor.build_tta_batch(sample_image_bytes)
        all_probs = loaded_registry.classify(batch)
        old_probs = np.average(all_probs, axis=0, weights=np.array(weights)).astype(np.float64)

        handler = AntiSpoofNetV4Handler(test_settings, model_registry=loaded_registry)
        handler.load(Path(test_settings.model_path))
        new_result = handler.infer_tta(sample_image_bytes)
        new_probs = np.array(new_result.probabilities, dtype=np.float64)

        assert np.allclose(old_probs, new_probs, atol=1e-6), (
            f"TTA divergence detected. old={old_probs.tolist()} new={new_probs.tolist()}"
        )
        assert len(new_result.probabilities) == 6

    def test_warmup_runs_without_raising(
        self, test_settings: Settings, loaded_registry
    ) -> None:
        from spectre.infrastructure.ml.handlers.antispoofnet_v4 import AntiSpoofNetV4Handler

        handler = AntiSpoofNetV4Handler(test_settings, model_registry=loaded_registry)
        handler.load(Path(test_settings.model_path))
        assert handler.is_loaded is True
