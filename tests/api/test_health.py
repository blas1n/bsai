"""Health endpoint tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestCheckDatabase:
    """Tests for check_database helper function."""

    @pytest.mark.asyncio
    async def test_returns_healthy_when_db_connected(self) -> None:
        """Returns 'healthy' when database query succeeds."""
        from bsai.api.routers.health import check_database

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        mock_manager = MagicMock()

        async def mock_get_session():
            yield mock_session

        mock_manager.get_session = mock_get_session

        with patch("bsai.api.routers.health.get_session_manager", return_value=mock_manager):
            result = await check_database()

        assert result == "healthy"

    @pytest.mark.asyncio
    async def test_returns_unhealthy_when_db_fails(self) -> None:
        """Returns 'unhealthy' when database query raises exception."""
        from bsai.api.routers.health import check_database

        with patch(
            "bsai.api.routers.health.get_session_manager",
            side_effect=Exception("Connection refused"),
        ):
            result = await check_database()

        assert result == "unhealthy"


class TestCheckRedis:
    """Tests for check_redis helper function."""

    @pytest.mark.asyncio
    async def test_returns_healthy_when_redis_connected(self) -> None:
        """Returns 'healthy' when Redis ping succeeds."""
        from bsai.api.routers.health import check_redis

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis.client = AsyncMock()
        mock_redis.client.ping = AsyncMock(return_value=True)

        with patch("bsai.api.routers.health.get_redis", return_value=mock_redis):
            result = await check_redis()

        assert result == "healthy"

    @pytest.mark.asyncio
    async def test_returns_unhealthy_when_redis_not_connected(self) -> None:
        """Returns 'unhealthy' when Redis is not connected."""
        from bsai.api.routers.health import check_redis

        mock_redis = MagicMock()
        mock_redis.is_connected = False

        with patch("bsai.api.routers.health.get_redis", return_value=mock_redis):
            result = await check_redis()

        assert result == "unhealthy"

    @pytest.mark.asyncio
    async def test_returns_unhealthy_when_redis_raises(self) -> None:
        """Returns 'unhealthy' when Redis ping raises exception."""
        from bsai.api.routers.health import check_redis

        with patch(
            "bsai.api.routers.health.get_redis",
            side_effect=Exception("Redis unavailable"),
        ):
            result = await check_redis()

        assert result == "unhealthy"


class TestHealthEndpoints:
    """Health check endpoint tests."""

    def test_health_returns_healthy(self, client: TestClient) -> None:
        """Health endpoint returns status healthy (liveness probe)."""
        # Health endpoint is a liveness probe - doesn't check dependencies
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_ready_returns_ready(self, client: TestClient) -> None:
        """Ready endpoint returns status ready when all services are up."""
        with (
            patch(
                "bsai.api.routers.health.check_database",
                new_callable=AsyncMock,
                return_value="healthy",
            ),
            patch(
                "bsai.api.routers.health.check_redis",
                new_callable=AsyncMock,
                return_value="healthy",
            ),
        ):
            response = client.get("/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            # Ready endpoint doesn't return version
            assert data["database"] == "healthy"
            assert data["redis"] == "healthy"

    def test_ready_returns_503_when_db_unhealthy(self, client: TestClient) -> None:
        """Ready endpoint returns 503 when database is unhealthy."""
        with (
            patch(
                "bsai.api.routers.health.check_database",
                new_callable=AsyncMock,
                return_value="unhealthy",
            ),
            patch(
                "bsai.api.routers.health.check_redis",
                new_callable=AsyncMock,
                return_value="healthy",
            ),
        ):
            response = client.get("/ready")

            assert response.status_code == 503
            data = response.json()
            assert "database" in data["error"]

    def test_ready_returns_503_when_redis_unhealthy(self, client: TestClient) -> None:
        """Ready endpoint returns 503 when redis is unhealthy."""
        with (
            patch(
                "bsai.api.routers.health.check_database",
                new_callable=AsyncMock,
                return_value="healthy",
            ),
            patch(
                "bsai.api.routers.health.check_redis",
                new_callable=AsyncMock,
                return_value="unhealthy",
            ),
        ):
            response = client.get("/ready")

            assert response.status_code == 503
            data = response.json()
            assert "redis" in data["error"]
