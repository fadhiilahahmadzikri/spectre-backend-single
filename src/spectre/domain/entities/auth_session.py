"""AuthSession entity — tracks a single face registration or authentication attempt."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID


SessionType = Literal["registration", "authentication", "replacement"]
SessionStatus = Literal[
    "PROCESSING",
    "REGISTERED",
    "AUTHENTICATED",
    "REJECTED",
    "FAILED",
    "SPOOF_DETECTED",
]


@dataclass
class AuthSession:
    """Tracks a single face operation (registration or authentication).

    Created when the API receives a face request. Updated with results
    after inference completes. Used for session polling and webhook payload.
    """

    id: UUID
    app_id: UUID
    session_type: SessionType
    status: SessionStatus = "PROCESSING"
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
    def is_live(self) -> bool:
        return self.liveness_class == "realperson"

    @property
    def is_match(self) -> bool:
        """Check if similarity exceeds threshold (set at use-case level)."""
        return self.similarity_score is not None and self.status == "AUTHENTICATED"
