"""Face operation domain exceptions."""

from __future__ import annotations

from spectre.domain.exceptions.base import SpectreError


class FaceAlreadyRegisteredError(SpectreError):
    error_code = "FACE_ALREADY_REGISTERED"
    http_status = 409

    def __init__(
        self, message: str = "A face profile already exists for this external_user_id."
    ) -> None:
        super().__init__(message)


class FaceProfileNotFoundError(SpectreError):
    error_code = "FACE_PROFILE_NOT_FOUND"
    http_status = 404

    def __init__(self, message: str = "Face profile not found.") -> None:
        super().__init__(message)


class LivenessCheckFailedError(SpectreError):
    error_code = "LIVENESS_CHECK_FAILED"
    http_status = 422

    def __init__(
        self,
        message: str | None = None,
        *,
        spoof_class: str | None = None,
        confidence: float | None = None,
        probabilities: tuple[float, ...] | None = None,
    ) -> None:
        if not message:
            if spoof_class == "realperson" and confidence is not None:
                message = f"Liveness check failed. Confidence too low ({confidence:.2f})."
            else:
                message = "Liveness check failed. Spoofing detected."
        
        super().__init__(
            message,
            details={
                "spoof_class": spoof_class,
                "confidence": confidence,
                "probabilities": probabilities,
            },
        )


class NoFaceDetectedError(SpectreError):
    error_code = "NO_FACE_DETECTED"
    http_status = 422

    def __init__(self, message: str = "No face detected in the provided image.") -> None:
        super().__init__(message)


class ImageQualityInsufficientError(SpectreError):
    error_code = "IMAGE_QUALITY_INSUFFICIENT"
    http_status = 422

    def __init__(
        self, message: str = "Image quality is insufficient for face processing."
    ) -> None:
        super().__init__(message)


class FaceMatchFailedError(SpectreError):
    error_code = "FACE_MATCH_FAILED"
    http_status = 403

    def __init__(
        self,
        message: str = "Face does not match the registered profile.",
        *,
        similarity_score: float | None = None,
    ) -> None:
        super().__init__(message, details={"similarity_score": similarity_score})


class ModelInferenceError(SpectreError):
    error_code = "MODEL_INFERENCE_ERROR"
    http_status = 500

    def __init__(self, message: str = "ML model inference failed.") -> None:
        super().__init__(message)


class ModelNotLoadedError(SpectreError):
    error_code = "MODEL_NOT_LOADED"
    http_status = 503

    def __init__(
        self,
        message: str = "Requested FAS model is not loaded.",
        *,
        model_id: str | None = None,
        available: list[str] | None = None,
        load_errors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            details={
                "model_id": model_id,
                "available": available or [],
                "load_errors": load_errors or {},
            },
        )
