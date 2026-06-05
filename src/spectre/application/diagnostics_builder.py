from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field

from spectre.domain.value_objects.face_embedding import FaceEmbedding
from spectre.domain.value_objects.liveness_result import FAS_CLASSES, LivenessResult
from spectre.interface.schemas.diagnostics_schema import (
    EmbeddingDiagnostics,
    FASDiagnostics,
    FlagsDiagnostics,
    InferenceDiagnostics,
    ModelDiagnostics,
    OutcomeType,
    RequestMetadata,
    TimingBreakdown,
)


@dataclass
class DiagnosticsContext:
    app_id: uuid.UUID
    external_user_id: str | None = None
    session_id: uuid.UUID | None = None
    request_id: str | None = None
    validation_ms: int = 0
    fas_inference_ms: int = 0
    embedding_extraction_ms: int = 0
    matching_ms: int = 0
    model_id: str | None = None
    model_version: str | None = None
    model_supports_tta: bool = False
    used_tta: bool = False
    liveness: LivenessResult | None = None
    liveness_threshold: float = 0.5
    embedding: FaceEmbedding | None = None
    embedding_provider: str = "none"
    similarity_score: float | None = None
    similarity_threshold: float | None = None
    bypass_fas: bool = False
    ml_disabled: bool = False
    reason: str | None = None


def build_diagnostics(
    ctx: DiagnosticsContext,
    *,
    outcome: OutcomeType,
) -> InferenceDiagnostics:
    total_ms = (
        ctx.validation_ms
        + ctx.fas_inference_ms
        + ctx.embedding_extraction_ms
        + ctx.matching_ms
    )

    model = None
    if ctx.model_id and ctx.model_version is not None:
        model = ModelDiagnostics(
            model_id=ctx.model_id,
            version=ctx.model_version,
            supports_tta=ctx.model_supports_tta,
            used_tta=ctx.used_tta,
        )

    fas = None
    if ctx.liveness is not None:
        fas = FASDiagnostics(
            classes=list(FAS_CLASSES),
            probabilities=[round(p, 6) for p in ctx.liveness.probabilities],
            predicted_class=ctx.liveness.predicted_class,
            predicted_index=ctx.liveness.predicted_index,
            confidence=round(ctx.liveness.confidence, 6),
            is_live=ctx.liveness.is_live,
            threshold_used=ctx.liveness_threshold,
            top_spoof_class=(
                ctx.liveness.top_spoof_class
                if ctx.liveness.predicted_class != "realperson"
                or ctx.liveness.confidence < ctx.liveness_threshold
                else None
            ),
            spoof_probability=round(ctx.liveness.spoof_probability, 6),
        )

    embedding = None
    if ctx.embedding_provider != "none":
        match = None
        if ctx.similarity_score is not None and ctx.similarity_threshold is not None:
            match = ctx.similarity_score >= ctx.similarity_threshold
        embedding = EmbeddingDiagnostics(
            extracted=ctx.embedding is not None,
            provider=ctx.embedding_provider,
            dim=(len(ctx.embedding.vector) if ctx.embedding else None),
            similarity_score=(
                round(ctx.similarity_score, 6)
                if ctx.similarity_score is not None
                else None
            ),
            similarity_threshold=ctx.similarity_threshold,
            match=match,
        )

    return InferenceDiagnostics(
        outcome=outcome,
        model=model,
        fas=fas,
        embedding=embedding,
        timings=TimingBreakdown(
            validation_ms=ctx.validation_ms,
            fas_inference_ms=ctx.fas_inference_ms,
            embedding_extraction_ms=ctx.embedding_extraction_ms,
            matching_ms=ctx.matching_ms,
            total_ms=total_ms,
        ),
        flags=FlagsDiagnostics(
            bypass_fas=ctx.bypass_fas,
            ml_disabled=ctx.ml_disabled,
            detail_mode=True,
        ),
        request=RequestMetadata(
            request_id=ctx.request_id,
            app_id=str(ctx.app_id),
            external_user_id=ctx.external_user_id,
            session_id=str(ctx.session_id) if ctx.session_id else None,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
        reason=ctx.reason,
    )
