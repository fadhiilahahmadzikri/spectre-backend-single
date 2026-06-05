from __future__ import annotations

import datetime
import json
import statistics
import time
import uuid

from spectre.application.diagnostics_builder import DiagnosticsContext, build_diagnostics
from spectre.config import Settings
from spectre.core.logger import get_logger
from spectre.domain.exceptions.face_exceptions import ModelInferenceError
from spectre.domain.value_objects.liveness_result import LivenessResult
from spectre.infrastructure.ml.fas_model_registry import FASModelRegistry
from spectre.infrastructure.ml.image_preprocessor import ImagePreprocessor

logger = get_logger(__name__)


class BenchmarkDisabledError(Exception):
    pass


class RunBenchmark:
    def __init__(
        self,
        registry: FASModelRegistry,
        settings: Settings,
        preprocessor: ImagePreprocessor,
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._prep = preprocessor

    def execute(
        self,
        app_id: uuid.UUID,
        image_bytes: bytes,
        external_user_id: str | None = None,
        request_id: str | None = None,
    ) -> dict:
        if not self._settings.benchmark_enabled:
            raise BenchmarkDisabledError("Benchmark mode is not enabled in admin config.")

        is_valid, err = self._prep.validate_image(image_bytes)
        if not is_valid:
            raise ValueError(f"Image validation failed: {err}")

        try:
            participating = json.loads(self._settings.benchmark_models)
            if not isinstance(participating, list):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            participating = []

        if not participating:
            raise ValueError("No models configured for benchmark.")

        liveness_threshold = self._settings.liveness_threshold
        results: list[dict] = []

        logger.info(
            "benchmark_run_started | request_id={} | models={}",
            request_id,
            participating,
        )

        for model_id in participating:
            try:
                handler = self._registry.get(model_id)
                t_start = time.monotonic()
                if handler.supports_tta:
                    inference = handler.infer_tta(image_bytes)
                else:
                    inference = handler.infer(image_bytes)
                liveness = LivenessResult.from_probabilities(
                    probabilities=list(inference.probabilities),
                    threshold=liveness_threshold,
                    inference_time_ms=inference.inference_time_ms,
                )
                elapsed_ms = int((time.monotonic() - t_start) * 1000)

                ctx = DiagnosticsContext(
                    app_id=app_id,
                    external_user_id=external_user_id,
                    request_id=request_id,
                    fas_inference_ms=elapsed_ms,
                    model_id=handler.model_id,
                    model_version=handler.version,
                    model_supports_tta=handler.supports_tta,
                    used_tta=handler.supports_tta,
                    liveness=liveness,
                    liveness_threshold=liveness_threshold,
                    embedding_provider="none",
                )
                outcome = "auth_success" if liveness.is_live else "spoof_detected"
                diagnostics = build_diagnostics(ctx, outcome=outcome)

                results.append({
                    "model_id": handler.model_id,
                    "version": handler.version,
                    "status": "completed",
                    "diagnostics": diagnostics.model_dump(),
                    "error": None,
                })
                logger.info(
                    "benchmark_model_completed | request_id={} | model_id={} | latency_ms={} | predicted={} | is_live={}",
                    request_id,
                    handler.model_id,
                    elapsed_ms,
                    liveness.predicted_class,
                    liveness.is_live,
                )
            except Exception as exc:
                err_msg = f"{type(exc).__name__}: {exc}"
                results.append({
                    "model_id": model_id,
                    "version": "unknown",
                    "status": "failed",
                    "diagnostics": None,
                    "error": err_msg,
                })
                logger.warning(
                    "benchmark_model_failed | request_id={} | model_id={} | error={}",
                    request_id,
                    model_id,
                    err_msg,
                )

        completed = [r for r in results if r["status"] == "completed"]
        consensus = None
        if completed:
            real_probs: list[float] = []
            is_live_votes: list[bool] = []
            predicted_classes: list[str] = []
            for r in completed:
                d = r["diagnostics"]
                if d and d.get("fas"):
                    fas = d["fas"]
                    real_probs.append(fas["probabilities"][5] if len(fas["probabilities"]) == 6 else 0.0)
                    is_live_votes.append(bool(fas["is_live"]))
                    predicted_classes.append(fas["predicted_class"])
            mean = statistics.mean(real_probs) if real_probs else 0.0
            stdev = statistics.stdev(real_probs) if len(real_probs) > 1 else 0.0
            consensus = {
                "is_live_agreement": len(set(is_live_votes)) <= 1,
                "predicted_class_agreement": len(set(predicted_classes)) <= 1,
                "mean_realperson_prob": round(mean, 6),
                "std_realperson_prob": round(stdev, 6),
                "unique_predicted_classes": list(set(predicted_classes)),
            }

        return {
            "request_id": request_id,
            "benchmark_enabled": True,
            "participating_models": participating,
            "results": results,
            "consensus": consensus,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
