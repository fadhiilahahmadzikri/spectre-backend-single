"""FaceProfile entity — stored face embedding for identity matching."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class FaceProfile:
    """Represents a registered face profile for a specific user within an application.

    The embedding is stored AES-256-GCM encrypted as bytes. Decryption and
    cosine similarity are performed in-process via NumPy.
    """

    id: UUID
    app_id: UUID
    external_user_id: str  # Tenant's user identifier
    embedding_encrypted: bytes  # AES-256-GCM encrypted 512-dim float32 vector
    model_version: str = "AntiSpoofNetV4"
    is_active: bool = True
    created_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
