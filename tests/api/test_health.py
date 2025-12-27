"""Health endpoint tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Health check endpoint tests."""

    def test_health_returns_healthy(self, client: TestClient) -> None:
        """Health endpoint returns status healthy."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_ready_returns_ready(self, client: TestClient) -> None:
        """Ready endpoint returns status ready."""
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "version" in data
