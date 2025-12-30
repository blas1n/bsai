"""Session router tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.auth import get_current_user_id
from agent.api.dependencies import get_cache, get_db
from agent.api.exceptions import AccessDeniedError, InvalidStateError, NotFoundError
from agent.api.handlers import register_exception_handlers
from agent.api.routers.sessions import router
from agent.api.schemas import (
    PaginatedResponse,
    SessionDetailResponse,
    SessionResponse,
)
from agent.db.models.enums import SessionStatus

if TYPE_CHECKING:
    pass


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")

    # Override dependencies
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


class TestCreateSession:
    """Tests for POST /sessions endpoint."""

    def test_creates_session_successfully(self, client: TestClient) -> None:
        """Creates a new session."""
        session_id = uuid4()
        mock_response = SessionResponse(
            id=session_id,
            user_id="test-user-123",
            status=SessionStatus.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("0"),
            context_usage_ratio=0.0,
        )

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_session = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.post(
                "/api/v1/sessions",
                json={"metadata": {"key": "value"}},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["status"] == "active"

    def test_creates_session_without_metadata(self, client: TestClient) -> None:
        """Creates session without metadata."""
        session_id = uuid4()
        mock_response = SessionResponse(
            id=session_id,
            user_id="test-user-123",
            status=SessionStatus.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("0"),
            context_usage_ratio=0.0,
        )

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_session = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/sessions", json={})

            assert response.status_code == 201


class TestListSessions:
    """Tests for GET /sessions endpoint."""

    def test_lists_user_sessions(self, client: TestClient) -> None:
        """Lists sessions for authenticated user."""
        sessions = [
            SessionResponse(
                id=uuid4(),
                user_id="test-user-123",
                status=SessionStatus.ACTIVE,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                total_input_tokens=50,
                total_output_tokens=50,
                total_cost_usd=Decimal("0.01"),
                context_usage_ratio=0.1,
            )
            for _ in range(3)
        ]
        mock_response = PaginatedResponse(
            items=sessions,
            total=3,
            limit=20,
            offset=0,
            has_more=False,
        )

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_sessions = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/sessions")

            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 3
            assert data["has_more"] is False

    def test_filters_by_status(self, client: TestClient) -> None:
        """Filters sessions by status."""
        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_sessions = AsyncMock(
                return_value=PaginatedResponse(
                    items=[], total=0, limit=20, offset=0, has_more=False
                )
            )
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/sessions?status=paused")

            assert response.status_code == 200
            mock_service.list_sessions.assert_called_once()


class TestGetSession:
    """Tests for GET /sessions/{session_id} endpoint."""

    def test_returns_session_details(self, client: TestClient) -> None:
        """Returns detailed session information."""
        session_id = uuid4()
        mock_response = SessionDetailResponse(
            id=session_id,
            user_id="test-user-123",
            status=SessionStatus.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            total_input_tokens=250,
            total_output_tokens=250,
            total_cost_usd=Decimal("0.05"),
            context_usage_ratio=0.1,
            tasks=[],
            active_task=None,
        )

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_session = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["tasks"] == []

    def test_returns_404_for_missing_session(self, client: TestClient) -> None:
        """Returns 404 when session not found."""
        session_id = uuid4()

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_session = AsyncMock(side_effect=NotFoundError("Session", session_id))
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}")

            assert response.status_code == 404


class TestPauseSession:
    """Tests for PUT /sessions/{session_id}/pause endpoint."""

    def test_pauses_session(self, client: TestClient) -> None:
        """Pauses an active session."""
        session_id = uuid4()
        mock_response = SessionResponse(
            id=session_id,
            user_id="test-user-123",
            status=SessionStatus.PAUSED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("0"),
            context_usage_ratio=0.0,
        )

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.pause_session = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.put(f"/api/v1/sessions/{session_id}/pause")

            assert response.status_code == 200
            assert response.json()["status"] == "paused"

    def test_returns_400_for_invalid_state(self, client: TestClient) -> None:
        """Returns 400 when session cannot be paused."""
        session_id = uuid4()

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.pause_session = AsyncMock(
                side_effect=InvalidStateError(
                    resource="Session",
                    current_state="paused",
                    action="paused",
                )
            )
            mock_service_class.return_value = mock_service

            response = client.put(f"/api/v1/sessions/{session_id}/pause")

            assert response.status_code == 400


class TestResumeSession:
    """Tests for PUT /sessions/{session_id}/resume endpoint."""

    def test_resumes_session(self, client: TestClient) -> None:
        """Resumes a paused session."""
        session_id = uuid4()
        mock_response = SessionResponse(
            id=session_id,
            user_id="test-user-123",
            status=SessionStatus.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=Decimal("0"),
            context_usage_ratio=0.0,
        )

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.resume_session = AsyncMock(return_value=(mock_response, None))
            mock_service_class.return_value = mock_service

            response = client.put(f"/api/v1/sessions/{session_id}/resume")

            assert response.status_code == 200
            assert response.json()["status"] == "active"


class TestCompleteSession:
    """Tests for PUT /sessions/{session_id}/complete endpoint."""

    def test_completes_session(self, client: TestClient) -> None:
        """Completes a session."""
        session_id = uuid4()
        mock_response = SessionResponse(
            id=session_id,
            user_id="test-user-123",
            status=SessionStatus.COMPLETED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            total_input_tokens=500,
            total_output_tokens=500,
            total_cost_usd=Decimal("0.10"),
            context_usage_ratio=0.5,
        )

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.complete_session = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.put(f"/api/v1/sessions/{session_id}/complete")

            assert response.status_code == 200
            assert response.json()["status"] == "completed"


class TestDeleteSession:
    """Tests for DELETE /sessions/{session_id} endpoint."""

    def test_deletes_session(self, client: TestClient) -> None:
        """Deletes a completed session."""
        session_id = uuid4()

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.delete_session = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            response = client.delete(f"/api/v1/sessions/{session_id}")

            assert response.status_code == 204

    def test_returns_403_for_other_user(self, client: TestClient) -> None:
        """Returns 403 when user doesn't own session."""
        session_id = uuid4()

        with patch("agent.api.routers.sessions.SessionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.delete_session = AsyncMock(
                side_effect=AccessDeniedError("Session", session_id)
            )
            mock_service_class.return_value = mock_service

            response = client.delete(f"/api/v1/sessions/{session_id}")

            assert response.status_code == 403
