"""Snapshot router tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.auth import get_current_user_id
from agent.api.dependencies import get_cache, get_db
from agent.api.exceptions import NotFoundError
from agent.api.handlers import register_exception_handlers
from agent.api.routers.snapshots import router
from agent.api.schemas import SnapshotResponse
from agent.db.models.enums import SnapshotType

if TYPE_CHECKING:
    pass


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")

    async def mock_get_db():
        yield MagicMock()

    async def mock_get_cache(redis=None):
        return MagicMock()

    async def mock_get_user_id():
        return "test-user-123"

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_cache] = mock_get_cache
    app.dependency_overrides[get_current_user_id] = mock_get_user_id

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


def create_mock_snapshot(session_id):
    """Create a mock snapshot response."""
    return SnapshotResponse(
        id=uuid4(),
        session_id=session_id,
        snapshot_type=SnapshotType.MANUAL,
        compressed_context="Compressed context data",
        key_decisions={"key": "value"},
        token_count=500,
        created_at=datetime.now(UTC),
    )


class TestListSnapshots:
    """Tests for GET /sessions/{session_id}/snapshots endpoint."""

    def test_returns_snapshot_list(self, client: TestClient) -> None:
        """Returns list of snapshots for a session."""
        session_id = uuid4()
        mock_snapshots = [create_mock_snapshot(session_id) for _ in range(3)]

        with patch("agent.api.routers.snapshots.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_snapshots = AsyncMock(return_value=mock_snapshots)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/snapshots")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3

    def test_returns_empty_list_when_no_snapshots(self, client: TestClient) -> None:
        """Returns empty list when session has no snapshots."""
        session_id = uuid4()

        with patch("agent.api.routers.snapshots.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_snapshots = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/snapshots")

            assert response.status_code == 200
            assert response.json() == []

    def test_returns_404_for_missing_session(self, client: TestClient) -> None:
        """Returns 404 when session not found."""
        session_id = uuid4()

        with patch("agent.api.routers.snapshots.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_snapshots = AsyncMock(
                side_effect=NotFoundError("Session", session_id)
            )
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/snapshots")

            assert response.status_code == 404


class TestCreateSnapshot:
    """Tests for POST /sessions/{session_id}/snapshots endpoint."""

    def test_creates_snapshot(self, client: TestClient) -> None:
        """Creates a manual snapshot."""
        session_id = uuid4()
        mock_snapshot = create_mock_snapshot(session_id)

        with patch("agent.api.routers.snapshots.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_snapshot = AsyncMock(return_value=mock_snapshot)
            mock_service_class.return_value = mock_service

            response = client.post(
                f"/api/v1/sessions/{session_id}/snapshots",
                json={"reason": "User requested backup"},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["snapshot_type"] == "manual"

    def test_returns_404_for_missing_session(self, client: TestClient) -> None:
        """Returns 404 when session not found."""
        session_id = uuid4()

        with patch("agent.api.routers.snapshots.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_snapshot = AsyncMock(
                side_effect=NotFoundError("Session", session_id)
            )
            mock_service_class.return_value = mock_service

            response = client.post(
                f"/api/v1/sessions/{session_id}/snapshots",
                json={"reason": "Test"},
            )

            assert response.status_code == 404


class TestGetLatestSnapshot:
    """Tests for GET /sessions/{session_id}/snapshots/latest endpoint."""

    def test_returns_latest_snapshot(self, client: TestClient) -> None:
        """Returns the most recent snapshot."""
        session_id = uuid4()
        mock_snapshot = create_mock_snapshot(session_id)

        with patch("agent.api.routers.snapshots.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_latest_snapshot = AsyncMock(return_value=mock_snapshot)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/snapshots/latest")

            assert response.status_code == 200
            data = response.json()
            assert data["compressed_context"] == "Compressed context data"

    def test_returns_404_when_no_snapshots(self, client: TestClient) -> None:
        """Returns 404 when no snapshots exist."""
        session_id = uuid4()

        with patch("agent.api.routers.snapshots.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_latest_snapshot = AsyncMock(
                side_effect=NotFoundError("Snapshot", "latest")
            )
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/snapshots/latest")

            assert response.status_code == 404


class TestGetSnapshot:
    """Tests for GET /sessions/{session_id}/snapshots/{snapshot_id} endpoint."""

    def test_returns_snapshot_details(self, client: TestClient) -> None:
        """Returns snapshot details."""
        session_id = uuid4()
        snapshot_id = uuid4()
        mock_snapshot = SnapshotResponse(
            id=snapshot_id,
            session_id=session_id,
            snapshot_type=SnapshotType.MANUAL,
            compressed_context="Detailed context",
            key_decisions={"decision": "made"},
            token_count=1000,
            created_at=datetime.now(UTC),
        )

        with patch("agent.api.routers.snapshots.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_snapshot = AsyncMock(return_value=mock_snapshot)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/snapshots/{snapshot_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["token_count"] == 1000

    def test_returns_404_for_missing_snapshot(self, client: TestClient) -> None:
        """Returns 404 when snapshot not found."""
        session_id = uuid4()
        snapshot_id = uuid4()

        with patch("agent.api.routers.snapshots.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_snapshot = AsyncMock(
                side_effect=NotFoundError("Snapshot", snapshot_id)
            )
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/snapshots/{snapshot_id}")

            assert response.status_code == 404
