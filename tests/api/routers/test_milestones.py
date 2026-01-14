"""Milestone router tests."""

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
from agent.api.dependencies import (
    get_breakpoint_service,
    get_cache,
    get_db,
    get_event_bus,
    get_ws_manager,
)
from agent.api.exceptions import NotFoundError
from agent.api.handlers import register_exception_handlers
from agent.api.routers.milestones import router
from agent.api.schemas import MilestoneDetailResponse, MilestoneResponse
from agent.db.models.enums import MilestoneStatus, TaskComplexity

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

    def mock_get_ws_manager():
        return MagicMock()

    def mock_get_event_bus():
        mock_bus = MagicMock()
        mock_bus.emit = AsyncMock()
        return mock_bus

    def mock_get_breakpoint_service():
        return MagicMock()

    async def mock_get_user_id():
        return "test-user-123"

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_cache] = mock_get_cache
    app.dependency_overrides[get_ws_manager] = mock_get_ws_manager
    app.dependency_overrides[get_event_bus] = mock_get_event_bus
    app.dependency_overrides[get_breakpoint_service] = mock_get_breakpoint_service
    app.dependency_overrides[get_current_user_id] = mock_get_user_id

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


def create_mock_milestone(task_id):
    """Create a mock milestone response."""
    return MilestoneResponse(
        id=uuid4(),
        task_id=task_id,
        sequence_number=1,
        title="Test Milestone",
        complexity=TaskComplexity.SIMPLE,
        status=MilestoneStatus.PASSED,
        selected_llm="gpt-4",
        retry_count=0,
        input_tokens=100,
        output_tokens=50,
        cost_usd=Decimal("0.005"),
        created_at=datetime.now(UTC),
    )


class TestListMilestones:
    """Tests for GET /tasks/{task_id}/milestones endpoint."""

    def test_returns_milestone_list(self, client: TestClient) -> None:
        """Returns list of milestones for a task."""
        task_id = uuid4()
        mock_milestones = [create_mock_milestone(task_id) for _ in range(3)]

        with patch("agent.api.routers.milestones.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_milestones = AsyncMock(return_value=mock_milestones)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/tasks/{task_id}/milestones")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3

    def test_returns_empty_list_when_no_milestones(self, client: TestClient) -> None:
        """Returns empty list when task has no milestones."""
        task_id = uuid4()

        with patch("agent.api.routers.milestones.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_milestones = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/tasks/{task_id}/milestones")

            assert response.status_code == 200
            assert response.json() == []

    def test_returns_404_for_missing_task(self, client: TestClient) -> None:
        """Returns 404 when task not found."""
        task_id = uuid4()

        with patch("agent.api.routers.milestones.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_milestones = AsyncMock(side_effect=NotFoundError("Task", task_id))
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/tasks/{task_id}/milestones")

            assert response.status_code == 404


class TestGetMilestone:
    """Tests for GET /tasks/{task_id}/milestones/{milestone_id} endpoint."""

    def test_returns_milestone_details(self, client: TestClient) -> None:
        """Returns detailed milestone information."""
        task_id = uuid4()
        milestone_id = uuid4()

        mock_response = MilestoneDetailResponse(
            id=milestone_id,
            task_id=task_id,
            sequence_number=1,
            title="Test Milestone",
            complexity=TaskComplexity.SIMPLE,
            status=MilestoneStatus.PASSED,
            selected_llm="gpt-4",
            retry_count=0,
            input_tokens=100,
            output_tokens=50,
            cost_usd=Decimal("0.005"),
            created_at=datetime.now(UTC),
            worker_output="Completed work",
            qa_result=None,
            acceptance_criteria=None,
        )

        with patch("agent.api.routers.milestones.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_milestone = AsyncMock(return_value=mock_response)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/tasks/{task_id}/milestones/{milestone_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["worker_output"] == "Completed work"

    def test_returns_404_for_missing_milestone(self, client: TestClient) -> None:
        """Returns 404 when milestone not found."""
        task_id = uuid4()
        milestone_id = uuid4()

        with patch("agent.api.routers.milestones.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_milestone = AsyncMock(
                side_effect=NotFoundError("Milestone", milestone_id)
            )
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/tasks/{task_id}/milestones/{milestone_id}")

            assert response.status_code == 404
