from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from spectre.infrastructure.ml.handlers.base import BaseFASHandler, FASInferenceResult


class _StubFASHandler(BaseFASHandler):
    def __init__(self) -> None:
        self._loaded = False
        self.preprocess_mock = MagicMock(return_value=np.zeros((1, 1), dtype=np.float32))
        self.predict_mock = MagicMock(
            return_value=np.array([[0.1, 0.1, 0.1, 0.1, 0.1, 0.5]], dtype=np.float32)
        )
        self.postprocess_mock = MagicMock(return_value=[0.1, 0.1, 0.1, 0.1, 0.1, 0.5])
        self.call_order: list[str] = []

    @property
    def model_id(self) -> str:
        return "stub_v1"

    @property
    def version(self) -> str:
        return "0.0.1"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self, artifact_path: Path) -> None:
        self._loaded = True

    def preprocess(self, image_bytes: bytes) -> np.ndarray:
        self.call_order.append("preprocess")
        return self.preprocess_mock(image_bytes)

    def predict(self, preprocessed: np.ndarray) -> np.ndarray:
        self.call_order.append("predict")
        return self.predict_mock(preprocessed)

    def postprocess(self, raw_output: np.ndarray) -> list[float]:
        self.call_order.append("postprocess")
        return self.postprocess_mock(raw_output)


class _IncompleteHandler(BaseFASHandler):
    @property
    def model_id(self) -> str:
        return "incomplete"


class TestBaseFASHandler:
    def test_cannot_instantiate_abstract_base_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseFASHandler()  # type: ignore[abstract]

    def test_incomplete_subclass_fails_to_instantiate(self) -> None:
        with pytest.raises(TypeError):
            _IncompleteHandler()  # type: ignore[abstract]

    def test_complete_subclass_can_be_instantiated(self) -> None:
        handler = _StubFASHandler()
        assert handler.model_id == "stub_v1"
        assert handler.version == "0.0.1"
        assert handler.is_loaded is False
        assert handler.supports_tta is False

    def test_load_updates_is_loaded(self) -> None:
        handler = _StubFASHandler()
        handler.load(Path("/nonexistent"))
        assert handler.is_loaded is True

    def test_infer_orchestrates_pipeline_in_correct_order(self) -> None:
        handler = _StubFASHandler()
        result = handler.infer(b"fake_image_bytes")
        assert handler.call_order == ["preprocess", "predict", "postprocess"]
        assert isinstance(result, FASInferenceResult)

    def test_infer_returns_valid_result_dataclass(self) -> None:
        handler = _StubFASHandler()
        result = handler.infer(b"fake_image_bytes")
        assert result.probabilities == [0.1, 0.1, 0.1, 0.1, 0.1, 0.5]
        assert result.inference_time_ms >= 0
        assert result.model_id == "stub_v1"
        assert result.model_version == "0.0.1"

    def test_infer_passes_image_bytes_to_preprocess(self) -> None:
        handler = _StubFASHandler()
        image_bytes = b"test_data"
        handler.infer(image_bytes)
        handler.preprocess_mock.assert_called_once_with(image_bytes)

    def test_infer_tta_raises_by_default(self) -> None:
        handler = _StubFASHandler()
        with pytest.raises(NotImplementedError, match="stub_v1 does not support TTA"):
            handler.infer_tta(b"image_bytes")

    def test_repr_contains_handler_metadata(self) -> None:
        handler = _StubFASHandler()
        representation = repr(handler)
        assert "_StubFASHandler" in representation
        assert "stub_v1" in representation
        assert "0.0.1" in representation
        assert "loaded=False" in representation


class TestFASInferenceResult:
    def test_dataclass_is_frozen(self) -> None:
        result = FASInferenceResult(
            probabilities=[0.1, 0.9],
            inference_time_ms=10,
            model_id="m",
            model_version="1",
        )
        with pytest.raises(Exception):
            result.probabilities = [0.5, 0.5]  # type: ignore[misc]

    def test_dataclass_fields(self) -> None:
        result = FASInferenceResult(
            probabilities=[0.1, 0.9],
            inference_time_ms=42,
            model_id="foo",
            model_version="bar",
        )
        assert result.probabilities == [0.1, 0.9]
        assert result.inference_time_ms == 42
        assert result.model_id == "foo"
        assert result.model_version == "bar"
