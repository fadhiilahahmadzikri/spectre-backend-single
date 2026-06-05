"""WebhookDelivery entity — tracks webhook dispatch attempts and retries."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID


DeliveryStatus = Literal["PENDING", "DELIVERED", "FAILED", "DEAD"]


@dataclass
class WebhookDelivery:
    """Tracks a single webhook delivery attempt to a tenant's configured URL.

    Supports exponential backoff retry with a maximum of 4 attempts.
    Marked DEAD after all retries are exhausted.
    """

    id: UUID
    session_id: UUID
    app_id: UUID
    status: DeliveryStatus = "PENDING"
    attempt_count: int = 0
    max_attempts: int = 4
    last_status_code: int | None = None
    last_error: str | None = None
    payload_hash: str | None = None
    next_retry_at: datetime.datetime | None = None
    delivered_at: datetime.datetime | None = None
    created_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)

    @property
    def can_retry(self) -> bool:
        return self.attempt_count < self.max_attempts and self.status == "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self.status in ("DELIVERED", "DEAD")
