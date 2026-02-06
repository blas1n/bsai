"""Health endpoint tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


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
