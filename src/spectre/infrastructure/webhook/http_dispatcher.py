"""HTTP webhook dispatcher — sends signed payloads to tenant URLs.

Uses httpx for async HTTP with timeout and error handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from spectre.config import Settings
from spectre.core.logger import get_logger
from spectre.infrastructure.webhook.hmac_signer import HMACSigner

logger = get_logger(__name__)


@dataclass
class DeliveryResult:
    """Result of a webhook delivery attempt."""

    success: bool
    status_code: int | None = None
    error: str | None = None


class WebhookDispatcher:
    """Dispatches signed webhook payloads to tenant URLs via HTTPS POST."""

    def __init__(self, settings: Settings) -> None:
        self._timeout = settings.webhook_timeout_seconds

    async def deliver(
        self,
        url: str,
        payload: dict[str, Any],
        secret: str,
    ) -> DeliveryResult:
        """Send a signed webhook payload to the tenant's URL.

        Args:
            url: The tenant's webhook endpoint URL.
            payload: The webhook payload dict.
            secret: The tenant's webhook secret (plaintext, decrypted).

        Returns:
            DeliveryResult with success status, HTTP code, and error details.
        """
        signature = HMACSigner.sign(payload, secret)

        headers = {
            "Content-Type": "application/json",
            "X-Spectre-Signature": signature,
            "User-Agent": "Spectre-Webhook/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)

            if 200 <= response.status_code < 300:
                logger.info(
                    "webhook_delivered",
                    url=url,
                    status_code=response.status_code,
                )
                return DeliveryResult(success=True, status_code=response.status_code)
            else:
                logger.warning(
                    "webhook_rejected",
                    url=url,
                    status_code=response.status_code,
                )
                return DeliveryResult(
                    success=False,
                    status_code=response.status_code,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )

        except httpx.TimeoutException:
            logger.warning("webhook_timeout", url=url)
            return DeliveryResult(success=False, error="Connection timed out")

        except httpx.ConnectError as exc:
            logger.warning("webhook_connect_error", url=url, error=str(exc))
            return DeliveryResult(success=False, error=f"Connection failed: {exc}")

        except Exception as exc:
            logger.error("webhook_unexpected_error", url=url, error=str(exc))
            return DeliveryResult(success=False, error=f"Unexpected error: {exc}")
