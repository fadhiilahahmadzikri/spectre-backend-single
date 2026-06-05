from __future__ import annotations

import datetime
import time
import uuid

from spectre.application.diagnostics_builder import DiagnosticsContext, build_diagnostics
from spectre.core.logger import get_logger
from spectre.domain.entities.auth_session import AuthSession
from spectre.domain.entities.face_profile import FaceProfile
from spectre.domain.exceptions.face_exceptions import (
    FaceAlreadyRegisteredError,
    FaceMatchFailedError,
    FaceProfileNotFoundError,
    ImageQualityInsufficientError,
    LivenessCheckFailedError,
)
from spectre.domain.ports.ml_ports import AbstractEmbeddingModel, AbstractFASModel
from spectre.domain.ports.repositories import (
    AbstractAuthSessionRepository,
    AbstractFaceProfileRepository,
)
from spectre.infrastructure.ml.image_preprocessor import ImagePreprocessor
from spectre.infrastructure.security.aes_encryption import AESEncryption
from spectre.interface.schemas.diagnostics_schema import InferenceDiagnostics

logger = get_logger(__name__)


def _extract_embedding(embed_model, image_bytes, preprocessor=None):
    try:
        return embed_model.extract_from_bytes(image_bytes)
    except NotImplementedError:
        if preprocessor is None:
            raise
        image = preprocessor.preprocess(image_bytes)
        return embed_model.extract(image)


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _active_model_meta(fas_model: AbstractFASModel) -> tuple[str | None, str | None, bool]:
    reg = getattr(fas_model, "_registry", None)
    settings = getattr(fas_model, "_settings", None)
    if reg is None or settings is None:
        return None, None, False
    try:
        handler = reg.get(settings.active_fas_model)
        return handler.model_id, handler.version, handler.supports_tta
    except Exception:
        return None, None, False


def _embedding_provider_name(embed_model: AbstractEmbeddingModel) -> str:
    cls = type(embed_model).__name__
    if "InsightFace" in cls:
        return "insightface"
    if "Keras" in cls:
        return "keras_fsfm"
    return "none"


class RegisterFace:
    def __init__(
        self,
        face_repo: AbstractFaceProfileRepository,
        session_repo: AbstractAuthSessionRepository,
        fas_model: AbstractFASModel,
        embedding_model: AbstractEmbeddingModel,
        preprocessor: ImagePreprocessor,
        encryption: AESEncryption,
    ) -> None:
        self._face_repo = face_repo
        self._session_repo = session_repo
        self._fas = fas_model
        self._embed = embedding_model
        self._prep = preprocessor
        self._enc = encryption

    async def execute(
        self,
        app_id: uuid.UUID,
        external_user_id: str,
        image_bytes: bytes,
        liveness_threshold: float = 0.5,
        metadata: dict | None = None,
        detail_mode: bool = False,
        request_id: str | None = None,
    ) -> tuple[AuthSession, InferenceDiagnostics | None]:
        ctx = DiagnosticsContext(
            app_id=app_id,
            external_user_id=external_user_id,
            request_id=request_id,
            liveness_threshold=liveness_threshold,
            bypass_fas=bool(metadata and metadata.get("bypass_fas") is True),
        )
        model_id, model_version, supports_tta = _active_model_meta(self._fas)
        ctx.model_id = model_id
        ctx.model_version = model_version
        ctx.model_supports_tta = supports_tta
        ctx.used_tta = supports_tta
        ctx.embedding_provider = _embedding_provider_name(self._embed)

        session = AuthSession(
            id=uuid.uuid4(), app_id=app_id,
            session_type="registration", status="PROCESSING",
            external_user_id=external_user_id, client_metadata=metadata,
        )
        session = await self._session_repo.create(session)
        ctx.session_id = session.id

        def _diag(outcome: str, reason: str | None = None) -> InferenceDiagnostics | None:
            if not detail_mode:
                return None
            ctx.reason = reason
            return build_diagnostics(ctx, outcome=outcome)

        try:
            existing = await self._face_repo.get_by_external_user(app_id, external_user_id)
            if existing:
                raise FaceAlreadyRegisteredError()

            t0 = time.monotonic()
            is_valid, err = self._prep.validate_image(image_bytes)
            ctx.validation_ms = _ms(t0)
            if not is_valid:
                raise ImageQualityInsufficientError(err)

            t_fas = time.monotonic()
            liveness = self._fas.predict_batch(image_bytes, threshold=liveness_threshold)
            ctx.fas_inference_ms = _ms(t_fas)
            ctx.liveness = liveness

            session.liveness_class = liveness.predicted_class
            session.liveness_confidence = liveness.confidence
            session.inference_time_ms = liveness.inference_time_ms

            if not liveness.is_live:
                if ctx.bypass_fas:
                    logger.warning(
                        "fas_bypassed_by_client | use_case=RegisterFace | user={} | spoof_class={} | confidence={}",
                        external_user_id,
                        liveness.predicted_class,
                        liveness.confidence,
                    )
                else:
                    session.status = "SPOOF_DETECTED"
                    session.completed_at = datetime.datetime.now(datetime.timezone.utc)
                    await self._session_repo.update(session)
                    report_class = (
                        liveness.top_spoof_class
                        if liveness.predicted_class == "realperson"
                        else liveness.predicted_class
                    )
                    exc_diag = _diag("spoof_detected", f"Detected spoof class: {report_class}")
                    exc = LivenessCheckFailedError(
                        spoof_class=report_class,
                        confidence=liveness.confidence,
                        probabilities=liveness.probabilities,
                    )
                    if exc_diag is not None:
                        exc.details = {**(exc.details or {}), "diagnostics": exc_diag.model_dump()}
                    raise exc

            t_emb = time.monotonic()
            embedding = _extract_embedding(self._embed, image_bytes, self._prep)
            ctx.embedding_extraction_ms = _ms(t_emb)
            ctx.embedding = embedding
            encrypted = self._enc.encrypt(embedding.to_bytes())

            profile = FaceProfile(
                id=uuid.uuid4(), app_id=app_id,
                external_user_id=external_user_id,
                embedding_encrypted=encrypted,
            )
            await self._face_repo.create(profile)

            session.status = "REGISTERED"
            if session.client_metadata is None:
                session.client_metadata = {}
            session.client_metadata["liveness_metrics"] = liveness.probabilities
            session.completed_at = datetime.datetime.now(datetime.timezone.utc)
            await self._session_repo.update(session)

            logger.info("face_registered | app_id={} | user={}", str(app_id), external_user_id)
            return session, _diag("registered")

        except FaceAlreadyRegisteredError:
            raise
        except ImageQualityInsufficientError:
            raise
        except LivenessCheckFailedError:
            raise
        except Exception as exc:
            session.status = "FAILED"
            session.completed_at = datetime.datetime.now(datetime.timezone.utc)
            await self._session_repo.update(session)
            logger.error("face_registration_failed | error={}", str(exc))
            raise


class AuthenticateFace:
    def __init__(
        self,
        face_repo: AbstractFaceProfileRepository,
        session_repo: AbstractAuthSessionRepository,
        fas_model: AbstractFASModel,
        embedding_model: AbstractEmbeddingModel,
        preprocessor: ImagePreprocessor,
        encryption: AESEncryption,
    ) -> None:
        self._face_repo = face_repo
        self._session_repo = session_repo
        self._fas = fas_model
        self._embed = embedding_model
        self._prep = preprocessor
        self._enc = encryption

    async def execute(
        self,
        app_id: uuid.UUID,
        external_user_id: str,
        image_bytes: bytes,
        liveness_threshold: float = 0.5,
        similarity_threshold: float = 0.75,
        metadata: dict | None = None,
        detail_mode: bool = False,
        request_id: str | None = None,
    ) -> tuple[AuthSession, InferenceDiagnostics | None]:
        ctx = DiagnosticsContext(
            app_id=app_id,
            external_user_id=external_user_id,
            request_id=request_id,
            liveness_threshold=liveness_threshold,
            similarity_threshold=similarity_threshold,
            bypass_fas=bool(metadata and metadata.get("bypass_fas") is True),
        )
        model_id, model_version, supports_tta = _active_model_meta(self._fas)
        ctx.model_id = model_id
        ctx.model_version = model_version
        ctx.model_supports_tta = supports_tta
        ctx.used_tta = supports_tta
        ctx.embedding_provider = _embedding_provider_name(self._embed)

        session = AuthSession(
            id=uuid.uuid4(), app_id=app_id,
            session_type="authentication", status="PROCESSING",
            external_user_id=external_user_id, client_metadata=metadata,
        )
        session = await self._session_repo.create(session)
        ctx.session_id = session.id

        def _diag(outcome: str, reason: str | None = None) -> InferenceDiagnostics | None:
            if not detail_mode:
                return None
            ctx.reason = reason
            return build_diagnostics(ctx, outcome=outcome)

        try:
            profile = await self._face_repo.get_by_external_user(app_id, external_user_id)
            if not profile:
                raise FaceProfileNotFoundError()

            t0 = time.monotonic()
            is_valid, err = self._prep.validate_image(image_bytes)
            ctx.validation_ms = _ms(t0)
            if not is_valid:
                raise ImageQualityInsufficientError(err)

            t_fas = time.monotonic()
            liveness = self._fas.predict_batch(image_bytes, threshold=liveness_threshold)
            ctx.fas_inference_ms = _ms(t_fas)
            ctx.liveness = liveness

            session.liveness_class = liveness.predicted_class
            session.liveness_confidence = liveness.confidence
            session.inference_time_ms = liveness.inference_time_ms

            if not liveness.is_live:
                if ctx.bypass_fas:
                    logger.warning(
                        "fas_bypassed_by_client | use_case=AuthenticateFace | user={} | spoof_class={} | confidence={}",
                        external_user_id,
                        liveness.predicted_class,
                        liveness.confidence,
                    )
                else:
                    session.status = "SPOOF_DETECTED"
                    session.completed_at = datetime.datetime.now(datetime.timezone.utc)
                    await self._session_repo.update(session)
                    report_class = (
                        liveness.top_spoof_class
                        if liveness.predicted_class == "realperson"
                        else liveness.predicted_class
                    )
                    exc_diag = _diag("spoof_detected", f"Detected spoof class: {report_class}")
                    exc = LivenessCheckFailedError(
                        spoof_class=report_class,
                        confidence=liveness.confidence,
                        probabilities=liveness.probabilities,
                    )
                    if exc_diag is not None:
                        exc.details = {**(exc.details or {}), "diagnostics": exc_diag.model_dump()}
                    raise exc

            from spectre.domain.value_objects.face_embedding import FaceEmbedding

            t_emb = time.monotonic()
            captured = _extract_embedding(self._embed, image_bytes, self._prep)
            ctx.embedding_extraction_ms = _ms(t_emb)
            ctx.embedding = captured

            decrypted = self._enc.decrypt(profile.embedding_encrypted)
            stored = FaceEmbedding.from_bytes(decrypted)

            t_match = time.monotonic()
            score = captured.cosine_similarity(stored)
            ctx.matching_ms = _ms(t_match)
            session.similarity_score = score
            ctx.similarity_score = score

            logger.info(
                "face_similarity_evaluated | user={} | similarity_score={} | threshold_required={}",
                external_user_id,
                score,
                similarity_threshold,
            )

            if score >= similarity_threshold:
                session.status = "AUTHENTICATED"
                logger.info("face_match_success | user={} | similarity_score={}", external_user_id, score)
            else:
                session.status = "REJECTED"
                session.completed_at = datetime.datetime.now(datetime.timezone.utc)
                await self._session_repo.update(session)
                logger.warning(
                    "face_match_rejected | user={} | similarity_score={} | reason=below_threshold",
                    external_user_id,
                    score,
                )
                exc_diag = _diag("auth_rejected", f"Similarity {round(score,4)} below threshold {similarity_threshold}")
                exc = FaceMatchFailedError(similarity_score=score)
                if exc_diag is not None:
                    exc.details = {**(exc.details or {}), "diagnostics": exc_diag.model_dump()}
                raise exc

            if session.client_metadata is None:
                session.client_metadata = {}
            session.client_metadata["liveness_metrics"] = liveness.probabilities
            session.completed_at = datetime.datetime.now(datetime.timezone.utc)
            await self._session_repo.update(session)

            logger.info(
                "face_authenticated | app_id={} | user={} | score={} | match={}",
                str(app_id),
                external_user_id,
                round(score, 4),
                session.status == "AUTHENTICATED",
            )
            return session, _diag("auth_success")

        except FaceProfileNotFoundError:
            raise
        except ImageQualityInsufficientError:
            raise
        except LivenessCheckFailedError:
            raise
        except FaceMatchFailedError:
            raise
        except Exception as exc:
            session.status = "FAILED"
            session.completed_at = datetime.datetime.now(datetime.timezone.utc)
            await self._session_repo.update(session)
            logger.error("face_auth_failed | error={}", str(exc))
            raise


class ReplaceFace:
    def __init__(
        self,
        face_repo: AbstractFaceProfileRepository,
        session_repo: AbstractAuthSessionRepository,
        fas_model: AbstractFASModel,
        embedding_model: AbstractEmbeddingModel,
        preprocessor: ImagePreprocessor,
        encryption: AESEncryption,
    ) -> None:
        self._face_repo = face_repo
        self._session_repo = session_repo
        self._fas = fas_model
        self._embed = embedding_model
        self._prep = preprocessor
        self._enc = encryption

    async def execute(
        self,
        app_id: uuid.UUID,
        external_user_id: str,
        image_bytes: bytes,
        liveness_threshold: float = 0.5,
        detail_mode: bool = False,
        request_id: str | None = None,
    ) -> tuple[AuthSession, InferenceDiagnostics | None]:
        ctx = DiagnosticsContext(
            app_id=app_id,
            external_user_id=external_user_id,
            request_id=request_id,
            liveness_threshold=liveness_threshold,
        )
        model_id, model_version, supports_tta = _active_model_meta(self._fas)
        ctx.model_id = model_id
        ctx.model_version = model_version
        ctx.model_supports_tta = supports_tta
        ctx.used_tta = False
        ctx.embedding_provider = _embedding_provider_name(self._embed)

        session = AuthSession(
            id=uuid.uuid4(), app_id=app_id,
            session_type="replacement", status="PROCESSING",
            external_user_id=external_user_id,
        )
        session = await self._session_repo.create(session)
        ctx.session_id = session.id

        def _diag(outcome: str, reason: str | None = None) -> InferenceDiagnostics | None:
            if not detail_mode:
                return None
            ctx.reason = reason
            return build_diagnostics(ctx, outcome=outcome)

        profile = await self._face_repo.get_by_external_user(app_id, external_user_id)
        if not profile:
            raise FaceProfileNotFoundError()

        t0 = time.monotonic()
        is_valid, err = self._prep.validate_image(image_bytes)
        ctx.validation_ms = _ms(t0)
        if not is_valid:
            raise ImageQualityInsufficientError(err)

        t_fas = time.monotonic()
        liveness = self._fas.predict(image_bytes, threshold=liveness_threshold)
        ctx.fas_inference_ms = _ms(t_fas)
        ctx.liveness = liveness

        session.liveness_class = liveness.predicted_class
        session.liveness_confidence = liveness.confidence
        session.inference_time_ms = liveness.inference_time_ms

        if not liveness.is_live:
            session.status = "SPOOF_DETECTED"
            session.completed_at = datetime.datetime.now(datetime.timezone.utc)
            await self._session_repo.update(session)
            report_class = (
                liveness.top_spoof_class
                if liveness.predicted_class == "realperson"
                else liveness.predicted_class
            )
            raise LivenessCheckFailedError(
                spoof_class=report_class, confidence=liveness.confidence,
            )

        t_emb = time.monotonic()
        embedding = _extract_embedding(self._embed, image_bytes, self._prep)
        ctx.embedding_extraction_ms = _ms(t_emb)
        ctx.embedding = embedding
        profile.embedding_encrypted = self._enc.encrypt(embedding.to_bytes())
        profile.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self._face_repo.update(profile)

        session.status = "REGISTERED"
        session.completed_at = datetime.datetime.now(datetime.timezone.utc)
        await self._session_repo.update(session)
        return session, _diag("registered")


class DeleteFace:
    def __init__(self, face_repo: AbstractFaceProfileRepository) -> None:
        self._face_repo = face_repo

    async def execute(self, app_id: uuid.UUID, external_user_id: str) -> None:
        profile = await self._face_repo.get_by_external_user(app_id, external_user_id)
        if not profile:
            raise FaceProfileNotFoundError()
        await self._face_repo.delete(app_id, external_user_id)
        logger.info("face_deleted | app_id={} | user={}", str(app_id), external_user_id)


class ListFaces:
    def __init__(self, face_repo: AbstractFaceProfileRepository) -> None:
        self._face_repo = face_repo

    async def execute(
        self, app_id: uuid.UUID, offset: int = 0, limit: int = 50
    ) -> list[FaceProfile]:
        return await self._face_repo.list_by_app(app_id, offset=offset, limit=limit)


class PurgeAllFaces:
    def __init__(self, face_repo: AbstractFaceProfileRepository) -> None:
        self._face_repo = face_repo

    async def execute(self, app_id: uuid.UUID) -> int:
        deleted_count = await self._face_repo.delete_all(app_id)
        logger.warning("faces_purged | app_id={} | count={}", str(app_id), deleted_count)
        return deleted_count
