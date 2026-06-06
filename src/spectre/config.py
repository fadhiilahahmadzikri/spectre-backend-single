"""Spectre application configuration via Pydantic BaseSettings.

All configuration is loaded from environment variables (or .env file).
This is the single source of truth for all application settings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "spectre"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "DEBUG"
    log_retention: str = "30 days"
    log_slow_query_ms: int = 500
    secret_key: str = "set-via-env"
    allowed_hosts: list[str] | str = "localhost,127.0.0.1"

    # --- Server ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1
    api_reload: bool = True

    # --- Database ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/spectre"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "spectre:"

    # --- JWT ---
    jwt_secret_key: str = "set-via-env"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # --- Security / Encryption ---
    encryption_key: str = "set-via-env-or-secrets"
    bcrypt_cost: int = 12
    api_key_length: int = 48
    static_api_key: str | None = None

    # --- Google OAuth ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = (
        "http://localhost:8000/api/v1/auth/oauth/google/callback"
    )
    oauth_frontend_redirect: str = "http://localhost:5173"

    # --- TOTP ---
    totp_issuer_name: str = "Spectre"

    # --- ML / Inference ---
    model_path: str = "artifact/best_model.keras"
    model_img_size: int = 256
    model_use_tta: bool = False
    inference_device: str = "cpu"

    # --- Multi-Model FAS Inference ---
    active_fas_model: str = "antispoofnet_v4"
    ilhamcaesar_model_path: str = "artifact/multimodel/ilhamcaesar/model_final_v1.2.keras"
    benchmark_enabled: bool = False
    benchmark_models: str = "[\"antispoofnet_v4\",\"ilhamcaesar_resnet50\"]"
    detail_mode_default: bool = False

    # --- InsightFace (ArcFace identity embeddings) ---
    insightface_model_name: str = "buffalo_l"
    insightface_model_root: str | None = None
    insightface_det_size: int = 640

    # --- Rate Limiting ---
    rate_limit_default: str = "100/minute"
    rate_limit_face_operations: str = "30/minute"

    # --- CORS ---
    cors_origins: list[str] | str = "http://localhost:3000,http://localhost:5173"
    cors_allow_credentials: bool = True

    # --- Face Matching ---
    similarity_threshold: float = 0.40
    liveness_threshold: float = 0.5

    @field_validator("allowed_hosts", "cors_origins", mode="before")
    @classmethod
    def parse_comma_separated(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated strings into list."""
        if isinstance(v, str):
            return [h.strip() for h in v.split(",") if h.strip()]
        return v

    @property
    def model_path_resolved(self) -> Path:
        """Resolve model path relative to project root."""
        path = Path(self.model_path)
        if path.is_absolute():
            return path
        return Path.cwd() / path

    @property
    def ilhamcaesar_model_path_resolved(self) -> Path:
        path = Path(self.ilhamcaesar_model_path)
        if path.is_absolute():
            return path
        return Path.cwd() / path

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def get_settings() -> Settings:
    """Factory function for settings singleton."""
    return Settings()
