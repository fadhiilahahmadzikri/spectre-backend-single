from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from spectre.config import Settings


_ARTIFACT_PATH = Path("artifact/multimodel/ilhamcaesar/model_final_v1.2.keras")


def _make_synthetic_jpeg_bytes(size: int = 224, seed: int = 2024) -> bytes:
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
    )


@pytest.fixture(scope="module")
def loaded_handler(test_settings: Settings):
    if not _ARTIFACT_PATH.exists():
        pytest.skip(f"IlhamCaesar ResNet50 artifact missing at {_ARTIFACT_PATH}")
    from spectre.infrastructure.ml.handlers.ilhamcaesar_resnet50 import IlhamCaesarResNet50Handler

    handler = IlhamCaesarResNet50Handler(test_settings)
    handler.load(_ARTIFACT_PATH)
    return handler


@pytest.fixture(scope="module")
def sample_image_bytes() -> bytes:
    return _make_synthetic_jpeg_bytes(size=300, seed=2024)


class TestIlhamCaesarResNet50Handler:
    def test_handler_metadata(self, loaded_handler) -> None:
        assert loaded_handler.model_id == "ilhamcaesar_resnet50"
        assert loaded_handler.version == "1.3"
        assert loaded_handler.supports_tta is False
        assert loaded_handler.is_loaded is True

    def test_preprocess_shape_and_dtype(
        self, loaded_handler, sample_image_bytes: bytes
    ) -> None:
        preprocessed = loaded_handler.preprocess(sample_image_bytes)
        assert preprocessed.shape == (1, 224, 224, 3)
        assert preprocessed.dtype == np.float32

    def test_preprocess_returns_raw_pixels(
        self, loaded_handler, sample_image_bytes: bytes
    ) -> None:
        # The saved .keras has `resnet50.preprocess_input` baked into its
        # Functional API graph (see multimodel/tensorflow/ilhamcaesar.ipynb
        # section "3. MODEL ARCHITECTURE"). The authentic notebook feeds RAW
        # [0, 255] pixel values directly into `model.predict(...)`. Applying
        # preprocess_input in the handler would double-apply BGR-swap and
        # mean subtraction, corrupting the input distribution.
        preprocessed = loaded_handler.preprocess(sample_image_bytes)
        assert preprocessed.min() >= 0.0
        assert preprocessed.max() <= 255.0

    def test_infer_returns_valid_probabilities(
        self, loaded_handler, sample_image_bytes: bytes
    ) -> None:
        result = loaded_handler.infer(sample_image_bytes)
        assert len(result.probabilities) == 6
        total = sum(result.probabilities)
        assert 0.99 <= total <= 1.01, f"Probabilities sum={total}, expected ~1.0"
        for p in result.probabilities:
            assert 0.0 <= p <= 1.0

    def test_infer_populates_metadata(
        self, loaded_handler, sample_image_bytes: bytes
    ) -> None:
        result = loaded_handler.infer(sample_image_bytes)
        assert result.model_id == "ilhamcaesar_resnet50"
        assert result.model_version == "1.3"
        assert result.inference_time_ms >= 0

    def test_infer_tta_raises_not_implemented(
        self, loaded_handler, sample_image_bytes: bytes
    ) -> None:
        with pytest.raises(NotImplementedError, match="ilhamcaesar_resnet50 does not support TTA"):
            loaded_handler.infer_tta(sample_image_bytes)

    def test_load_missing_artifact_raises(self, test_settings: Settings) -> None:
        from spectre.infrastructure.ml.handlers.ilhamcaesar_resnet50 import IlhamCaesarResNet50Handler

        handler = IlhamCaesarResNet50Handler(test_settings)
        with pytest.raises(FileNotFoundError):
            handler.load(Path("/nonexistent/model.keras"))
