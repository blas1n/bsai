"""Task router tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.auth import get_current_user_id
from agent.api.dependencies import get_cache, get_db, get_ws_manager
from agent.api.exceptions import AccessDeniedError, InvalidStateError, NotFoundError
from agent.api.handlers import register_exception_handlers
from agent.api.routers.tasks import router
from agent.api.schemas import (
    PaginatedResponse,
    TaskDetailResponse,
    TaskResponse,
)
from agent.db.models.enums import TaskStatus

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

    def mock_get_cache():
        return MagicMock()

    def mock_get_ws_manager():
        return MagicMock()

    async def mock_get_user_id():
        return "test-user-123"

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_cache] = mock_get_cache
    app.dependency_overrides[get_ws_manager] = mock_get_ws_manager
    app.dependency_overrides[get_current_user_id] = mock_get_user_id

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestCreateTask:
    """Tests for POST /sessions/{session_id}/tasks endpoint."""

    def test_creates_task_successfully(self, client: TestClient) -> None:
        """Creates and starts task execution."""
        session_id = uuid4()
        task_id = uuid4()

        mock_response = TaskResponse(
            id=task_id,
            session_id=session_id,
            original_request="Write a function",
            status=TaskStatus.PENDING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            final_result=None,
        )

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_and_execute_task = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.post(
                f"/api/v1/sessions/{session_id}/tasks",
                json={"original_request": "Write a function"},
            )

            assert response.status_code == 202
            data = response.json()
            assert data["status"] == "pending"

    def test_creates_task_with_streaming(self, client: TestClient) -> None:
        """Creates task with streaming enabled."""
        session_id = uuid4()
        task_id = uuid4()

        mock_response = TaskResponse(
            id=task_id,
            session_id=session_id,
            original_request="Write a function",
            status=TaskStatus.PENDING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            final_result=None,
        )

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_and_execute_task = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.post(
                f"/api/v1/sessions/{session_id}/tasks",
                json={"original_request": "Write a function", "stream": True},
            )

            assert response.status_code == 202

    def test_returns_404_for_missing_session(self, client: TestClient) -> None:
        """Returns 404 when session not found."""
        session_id = uuid4()

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_and_execute_task = AsyncMock(
                side_effect=NotFoundError("Session", session_id)
            )
            mock_service_class.return_value = mock_service

            response = client.post(
                f"/api/v1/sessions/{session_id}/tasks",
                json={"original_request": "Test"},
            )

            assert response.status_code == 404

    def test_returns_400_for_inactive_session(self, client: TestClient) -> None:
        """Returns 400 when session is not active."""
        session_id = uuid4()

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_and_execute_task = AsyncMock(
                side_effect=InvalidStateError(
                    resource="Session",
                    current_state="paused",
                    action="create tasks in",
                )
            )
            mock_service_class.return_value = mock_service

            response = client.post(
                f"/api/v1/sessions/{session_id}/tasks",
                json={"original_request": "Test"},
            )

            assert response.status_code == 400


class TestListTasks:
    """Tests for GET /sessions/{session_id}/tasks endpoint."""

    def test_lists_session_tasks(self, client: TestClient) -> None:
        """Lists tasks for a session."""
        session_id = uuid4()

        tasks = [
            TaskResponse(
                id=uuid4(),
                session_id=session_id,
                original_request=f"Request {i}",
                status=TaskStatus.COMPLETED,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                final_result="Result",
            )
            for i in range(3)
        ]
        mock_response = PaginatedResponse(
            items=tasks,
            total=3,
            limit=20,
            offset=0,
            has_more=False,
        )

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_tasks = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/tasks")

            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 3

    def test_filters_by_status(self, client: TestClient) -> None:
        """Filters tasks by status."""
        session_id = uuid4()

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_tasks = AsyncMock(
                return_value=PaginatedResponse(
                    items=[], total=0, limit=20, offset=0, has_more=False
                )
            )
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/tasks?status=in_progress")

            assert response.status_code == 200

    def test_supports_pagination(self, client: TestClient) -> None:
        """Supports pagination parameters."""
        session_id = uuid4()

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_tasks = AsyncMock(
                return_value=PaginatedResponse(
                    items=[], total=0, limit=10, offset=5, has_more=False
                )
            )
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/tasks?limit=10&offset=5")

            assert response.status_code == 200


class TestGetTask:
    """Tests for GET /sessions/{session_id}/tasks/{task_id} endpoint."""

    def test_returns_task_details(self, client: TestClient) -> None:
        """Returns task details with milestones."""
        session_id = uuid4()
        task_id = uuid4()

        mock_response = TaskDetailResponse(
            id=task_id,
            session_id=session_id,
            original_request="Test request",
            status=TaskStatus.COMPLETED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            final_result="Completed result",
            milestones=[],
            agent_steps=[],
            progress=1.0,
            total_duration_ms=None,
            cost_breakdown={},
        )

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/tasks/{task_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["progress"] == 1.0

    def test_returns_404_for_missing_task(self, client: TestClient) -> None:
        """Returns 404 when task not found."""
        session_id = uuid4()
        task_id = uuid4()

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task = AsyncMock(side_effect=NotFoundError("Task", task_id))
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/sessions/{session_id}/tasks/{task_id}")

            assert response.status_code == 404


class TestCancelTask:
    """Tests for PUT /sessions/{session_id}/tasks/{task_id}/cancel endpoint."""

    def test_cancels_running_task(self, client: TestClient) -> None:
        """Cancels a running task."""
        session_id = uuid4()
        task_id = uuid4()

        mock_response = TaskResponse(
            id=task_id,
            session_id=session_id,
            original_request="Test",
            status=TaskStatus.FAILED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            final_result="Task cancelled by user",
        )

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.cancel_task = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.put(f"/api/v1/sessions/{session_id}/tasks/{task_id}/cancel")

            assert response.status_code == 200
            assert response.json()["status"] == "failed"

    def test_returns_400_for_completed_task(self, client: TestClient) -> None:
        """Returns 400 when task is already completed."""
        session_id = uuid4()
        task_id = uuid4()

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.cancel_task = AsyncMock(
                side_effect=InvalidStateError(
                    resource="Task",
                    current_state="completed",
                    action="cancelled",
                )
            )
            mock_service_class.return_value = mock_service

            response = client.put(f"/api/v1/sessions/{session_id}/tasks/{task_id}/cancel")

            assert response.status_code == 400

    def test_returns_403_for_other_user(self, client: TestClient) -> None:
        """Returns 403 when user doesn't own task."""
        session_id = uuid4()
        task_id = uuid4()

        with patch("agent.api.routers.tasks.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.cancel_task = AsyncMock(side_effect=AccessDeniedError("Task", task_id))
            mock_service_class.return_value = mock_service

            response = client.put(f"/api/v1/sessions/{session_id}/tasks/{task_id}/cancel")

            assert response.status_code == 403
