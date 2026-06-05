"""Redis cache client — rate limiting and API key cache."""

from __future__ import annotations

from typing import Any

import redis.asyncio as redis

from spectre.config import Settings
from spectre.core.logger import get_logger

logger = get_logger(__name__)


class RedisClient:
    """Async Redis client for caching and rate limiting."""

    def __init__(self, settings: Settings) -> None:
        self._prefix = settings.redis_key_prefix
        self._client: redis.Redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

    def _key(self, key: str) -> str:
        """Prefix a key with the application namespace."""
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        return await self._client.get(self._key(key))

    async def set(
        self, key: str, value: str, *, expire_seconds: int | None = None
    ) -> None:
        """Set a key-value pair with optional expiry."""
        await self._client.set(self._key(key), value, ex=expire_seconds)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        await self._client.delete(self._key(key))

    async def incr(self, key: str) -> int:
        """Increment a counter and return the new value."""
        return await self._client.incr(self._key(key))

    async def expire(self, key: str, seconds: int) -> None:
        """Set expiry on a key."""
        await self._client.expire(self._key(key), seconds)

    async def ttl(self, key: str) -> int:
        """Get remaining TTL on a key."""
        return await self._client.ttl(self._key(key))

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._client.aclose()

    async def ping(self) -> bool:
        """Health check — returns True if Redis is reachable."""
        try:
            return await self._client.ping()
        except Exception:
            return False
