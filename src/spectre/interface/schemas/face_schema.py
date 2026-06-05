from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, Field

from spectre.interface.schemas.diagnostics_schema import InferenceDiagnostics


class FaceRegisterRequest(BaseModel):
    external_user_id: str = Field(..., max_length=255)
    image: str
    metadata: dict[str, Any] | None = None
    detail_mode: bool = False


class FaceAuthenticateRequest(BaseModel):
    external_user_id: str = Field(..., max_length=255)
    image: str
    metadata: dict[str, Any] | None = None
    detail_mode: bool = False


class FaceReplaceRequest(BaseModel):
    external_user_id: str = Field(..., max_length=255)
    image: str
    detail_mode: bool = False


class FaceBenchmarkRequest(BaseModel):
    external_user_id: str | None = Field(default=None, max_length=255)
    image: str


class FaceSessionResponse(BaseModel):
    session_id: str
    status: str
    created_at: datetime.datetime
    diagnostics: InferenceDiagnostics | None = None


class BenchmarkModelResult(BaseModel):
    model_id: str
    version: str
    status: str
    diagnostics: InferenceDiagnostics | None = None
    error: str | None = None


class BenchmarkConsensus(BaseModel):
    is_live_agreement: bool
    predicted_class_agreement: bool
    mean_realperson_prob: float
    std_realperson_prob: float
    unique_predicted_classes: list[str]


class FaceBenchmarkResponse(BaseModel):
    request_id: str | None
    benchmark_enabled: bool
    participating_models: list[str]
    results: list[BenchmarkModelResult]
    consensus: BenchmarkConsensus | None
    timestamp: datetime.datetime


class SessionDetailResponse(BaseModel):
    session_id: str
    session_type: str
    status: str
    external_user_id: str | None
    liveness_class: str | None
    liveness_confidence: float | None
    similarity_score: float | None
    inference_time_ms: int | None
    created_at: datetime.datetime
    completed_at: datetime.datetime | None
    diagnostics: InferenceDiagnostics | None = None
