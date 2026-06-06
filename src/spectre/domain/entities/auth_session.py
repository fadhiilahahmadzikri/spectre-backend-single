"""AuthSession entity — tracks a single face registration or authentication attempt."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID


SessionType = Literal["registration", "authentication", "replacement", "hosted_auth"]
SessionStatus = Literal[
    "PROCESSING",
    "REGISTERED",
    "AUTHENTICATED",
    "REJECTED",
    "FAILED",
    "SPOOF_DETECTED",
]
SessionLifecycleState = Literal[
    "PROCESSING",
    "CREATED",
    "LOCKED",
    "SUCCEEDED",
    "FAILED",
    "CANCELED",
    "EXPIRED",
]


@dataclass
class AuthSession:
    """Tracks a single face operation (registration or authentication).

    Created when the API receives a face request. Updated with results
    after inference completes. Used for session lookup.
    """

    id: UUID
    app_id: UUID
    session_type: SessionType
    status: SessionStatus = "PROCESSING"
    lifecycle_state: SessionLifecycleState = "PROCESSING"
    failure_reason: str | None = None
    expires_at: datetime.datetime | None = None
    idempotency_key: str | None = None
    sdk_version: str | None = None
    client_secret_hash: str | None = None
    return_url: str | None = None
    cancel_url: str | None = None
    locked_at: datetime.datetime | None = None
    exchange_code_hash: str | None = None
    exchange_code_expires_at: datetime.datetime | None = None
    exchanged_at: datetime.datetime | None = None
    external_user_id: str | None = None

    # --- Liveness (FAS) results ---
    liveness_class: str | None = None
    liveness_confidence: float | None = None

    # --- Similarity results (authentication only) ---
    similarity_score: float | None = None

    # --- Performance ---
    inference_time_ms: int | None = None

    # --- Metadata ---
    client_metadata: dict | None = None  # Passed through from client request

    created_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    completed_at: datetime.datetime | None = None

    @property
    def is_complete(self) -> bool:
        return self.status not in ("PROCESSING",)

    @property
    def is_terminal(self) -> bool:
        return self.lifecycle_state in ("SUCCEEDED", "FAILED", "CANCELED", "EXPIRED")

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None or self.lifecycle_state == "LOCKED"

    def mark_locked(self, now: datetime.datetime) -> None:
        if self.locked_at is None:
            self.locked_at = now
        if not self.is_terminal:
            self.lifecycle_state = "LOCKED"

    def mark_succeeded(self, now: datetime.datetime) -> None:
        self.lifecycle_state = "SUCCEEDED"
        self.completed_at = now

    def mark_failed(self, now: datetime.datetime, reason: str | None = None) -> None:
        self.lifecycle_state = "FAILED"
        self.failure_reason = reason
        self.completed_at = now

    @property
    def is_live(self) -> bool:
        return self.liveness_class == "realperson"

    @property
    def is_match(self) -> bool:
        """Check if similarity exceeds threshold (set at use-case level)."""
        return self.similarity_score is not None and self.status == "AUTHENTICATED"
