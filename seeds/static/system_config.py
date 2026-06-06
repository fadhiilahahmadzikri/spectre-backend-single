"""Seed: system_config — default operational parameters."""

from __future__ import annotations

from seeds.base import BaseSeeder

DEFAULTS = [
    # Anti-Spoofing & Liveness
    ("liveness_threshold", "0.5", "anti_spoofing", "float", "Minimum realperson probability for liveness pass"),
    ("similarity_threshold", "0.40", "anti_spoofing", "float", "Minimum cosine similarity for face match"),
    ("model_use_tta", "false", "anti_spoofing", "bool", "Enable Test-Time Augmentation for FAS inference"),
    ("active_fas_model", "antispoofnet_v4", "anti_spoofing", "string", "Active FAS model provider (switchable at runtime)"),
    ("benchmark_enabled", "false", "anti_spoofing", "bool", "Enable multi-model benchmark mode (side-by-side comparison)"),
    ("benchmark_models", "[\"antispoofnet_v4\",\"ilhamcaesar_resnet50\"]", "anti_spoofing", "string", "JSON array of FAS model_ids participating in benchmark"),
    ("detail_mode_default", "false", "anti_spoofing", "bool", "Default state of detail_mode toggle in the scan config drawer"),
    # Rate Limiting
    ("rate_limit_default", "100/minute", "rate_limiting", "string", "Default API rate limit"),
    ("rate_limit_face_operations", "30/minute", "rate_limiting", "string", "Rate limit for face operation endpoints"),
    # Session & Auth
    ("jwt_access_token_expire_minutes", "30", "session_auth", "int", "JWT access token lifetime in minutes"),
    ("jwt_refresh_token_expire_days", "7", "session_auth", "int", "JWT refresh token lifetime in days"),
    # Scan UX
    ("redirect_url", "https://www.youtube.com", "scan_ux", "string", "Default redirect URL after successful verification"),
    ("redirect_delay", "5", "scan_ux", "int", "Seconds to wait before redirecting after scan"),
    ("brightness_threshold", "55", "scan_ux", "int", "Minimum brightness level for camera feed validation"),
]


class SystemConfigSeeder(BaseSeeder):
    name = "system_config"
    order = 50

    async def run(self, session) -> None:
        from sqlalchemy import text

        for key, value, category, data_type, description in DEFAULTS:
            await session.execute(
                text(
                    "INSERT INTO system_config (key, value, category, data_type, description) "
                    "VALUES (:key, :value, :category, :data_type, :description) "
                    "ON CONFLICT (key) DO NOTHING"
                ),
                {"key": key, "value": value, "category": category, "data_type": data_type, "description": description},
            )
        await session.commit()
