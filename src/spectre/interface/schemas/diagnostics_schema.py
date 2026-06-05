from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


OutcomeType = Literal[
    "auth_success",
    "auth_rejected",
    "registered",
    "spoof_detected",
    "image_invalid",
    "profile_not_found",
    "already_registered",
    "ml_bypassed",
    "failed",
]


class ModelDiagnostics(BaseModel):
    model_id: str
    version: str
    supports_tta: bool
    used_tta: bool


class FASDiagnostics(BaseModel):
    classes: list[str]
    probabilities: list[float]
    predicted_class: str
    predicted_index: int
    confidence: float
    is_live: bool
    threshold_used: float
    top_spoof_class: str | None = None
    spoof_probability: float


class EmbeddingDiagnostics(BaseModel):
    extracted: bool
    provider: Literal["insightface", "keras_fsfm", "none"]
    dim: int | None = None
    similarity_score: float | None = None
    similarity_threshold: float | None = None
    match: bool | None = None


class TimingBreakdown(BaseModel):
    validation_ms: int = 0
    fas_inference_ms: int = 0
    embedding_extraction_ms: int = 0
    matching_ms: int = 0
    total_ms: int = 0


class FlagsDiagnostics(BaseModel):
    bypass_fas: bool = False
    ml_disabled: bool = False
    detail_mode: bool = True


class RequestMetadata(BaseModel):
    request_id: str | None = None
    app_id: str
    external_user_id: str | None = None
    session_id: str | None = None
    timestamp: str


class InferenceDiagnostics(BaseModel):
    outcome: OutcomeType
    model: ModelDiagnostics | None = None
    fas: FASDiagnostics | None = None
    embedding: EmbeddingDiagnostics | None = None
    timings: TimingBreakdown
    flags: FlagsDiagnostics
    request: RequestMetadata
    reason: str | None = Field(
        default=None,
        description="Human-readable reason for the outcome (e.g. bypass source, failure cause).",
    )
