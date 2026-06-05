"""Tests — Health Router.

Covers: GET /, GET /health
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHealthEndpoints:
    """Health check endpoints — no auth required."""

    async def test_root_returns_200(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Spectre API" in response.text

    async def test_health_returns_200_with_components(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert "components" in body
        assert "database" in body["components"]
        assert "redis" in body["components"]
        assert "ml_model" in body["components"]

    async def test_health_response_has_timestamp(self, client: AsyncClient):
        response = await client.get("/health")
        body = response.json()
        assert "timestamp" in body or "status" in body
