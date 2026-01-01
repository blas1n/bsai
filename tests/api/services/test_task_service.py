"""Task service tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.api.exceptions import AccessDeniedError, InvalidStateError, NotFoundError
from agent.api.schemas import TaskCreate
from agent.api.services.task_service import TaskService
from agent.db.models.enums import SessionStatus, TaskStatus

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create mock session cache."""
    cache = MagicMock()
    cache.invalidate_task_progress = AsyncMock()
    return cache


@pytest.fixture
def task_service(mock_db: AsyncMock, mock_cache: MagicMock) -> TaskService:
    """Create task service with mocked dependencies."""
    return TaskService(mock_db, mock_cache)


class TestCreateAndExecuteTask:
    """Tests for create_and_execute_task method."""

    @pytest.mark.asyncio
    async def test_creates_task_for_active_session(
        self,
        task_service: TaskService,
    ) -> None:
        """Creates task for an active session."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.ACTIVE.value

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id
        mock_task.original_request = "Test request"
        mock_task.status = TaskStatus.PENDING.value
        mock_task.created_at = datetime.now(UTC)
        mock_task.updated_at = datetime.now(UTC)
        mock_task.final_result = None
        mock_task.retry_count = 0

        request = TaskCreate(original_request="Test request", stream=False)

        with (
            patch.object(
                task_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_session,
            patch.object(
                task_service.task_repo,
                "create",
                new_callable=AsyncMock,
            ) as mock_create,
            patch("asyncio.create_task") as mock_create_task,
        ):
            mock_get_session.return_value = mock_session
            mock_create.return_value = mock_task

            result = await task_service.create_and_execute_task(session_id, user_id, request)

            assert result.id == task_id
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_session(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises NotFoundError when session doesn't exist."""
        session_id = uuid4()
        user_id = "user-123"
        request = TaskCreate(original_request="Test request")

        with patch.object(
            task_service.session_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None

            with pytest.raises(NotFoundError):
                await task_service.create_and_execute_task(session_id, user_id, request)

    @pytest.mark.asyncio
    async def test_raises_access_denied_for_other_user(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises AccessDeniedError for another user's session."""
        session_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = "other-user"

        request = TaskCreate(original_request="Test request")

        with patch.object(
            task_service.session_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_session

            with pytest.raises(AccessDeniedError):
                await task_service.create_and_execute_task(session_id, "user-123", request)

    @pytest.mark.asyncio
    async def test_raises_invalid_state_for_inactive_session(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises InvalidStateError for inactive session."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.PAUSED.value

        request = TaskCreate(original_request="Test request")

        with patch.object(
            task_service.session_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_session

            with pytest.raises(InvalidStateError):
                await task_service.create_and_execute_task(session_id, user_id, request)


class TestGetTask:
    """Tests for get_task method."""

    @pytest.mark.asyncio
    async def test_returns_task_details(
        self,
        task_service: TaskService,
    ) -> None:
        """Returns task details with milestones."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id
        mock_task.original_request = "Test request"
        mock_task.status = TaskStatus.IN_PROGRESS.value
        mock_task.created_at = datetime.now(UTC)
        mock_task.updated_at = datetime.now(UTC)
        mock_task.final_result = None
        mock_task.retry_count = 0

        with (
            patch.object(
                task_service.task_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_task,
            patch.object(
                task_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_session,
            patch.object(
                task_service.milestone_repo,
                "get_by_task_id",
                new_callable=AsyncMock,
            ) as mock_milestones,
        ):
            mock_get_task.return_value = mock_task
            mock_get_session.return_value = mock_session
            mock_milestones.return_value = []

            result = await task_service.get_task(task_id, user_id)

            assert result.id == task_id
            assert result.milestones == []
            assert result.progress == 0.0

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_task(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises NotFoundError when task doesn't exist."""
        task_id = uuid4()
        user_id = "user-123"

        with patch.object(
            task_service.task_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None

            with pytest.raises(NotFoundError):
                await task_service.get_task(task_id, user_id)


class TestListTasks:
    """Tests for list_tasks method."""

    @pytest.mark.asyncio
    async def test_returns_paginated_tasks(
        self,
        task_service: TaskService,
    ) -> None:
        """Returns paginated task list."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_tasks = [
            MagicMock(
                id=uuid4(),
                session_id=session_id,
                original_request=f"Request {i}",
                status=TaskStatus.COMPLETED.value,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                final_result="Result",
                retry_count=0,
            )
            for i in range(3)
        ]

        with (
            patch.object(
                task_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_session,
            patch.object(
                task_service.task_repo,
                "get_by_session_id",
                new_callable=AsyncMock,
            ) as mock_get_tasks,
        ):
            mock_get_session.return_value = mock_session
            mock_get_tasks.return_value = mock_tasks

            result = await task_service.list_tasks(session_id, user_id)

            assert len(result.items) == 3
            assert result.has_more is False


class TestCancelTask:
    """Tests for cancel_task method."""

    @pytest.mark.asyncio
    async def test_cancels_in_progress_task(
        self,
        task_service: TaskService,
        mock_cache: MagicMock,
    ) -> None:
        """Cancels an in-progress task."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id
        mock_task.status = TaskStatus.IN_PROGRESS.value

        mock_cancelled = MagicMock()
        mock_cancelled.id = task_id
        mock_cancelled.session_id = session_id
        mock_cancelled.original_request = "Test"
        mock_cancelled.status = TaskStatus.FAILED.value
        mock_cancelled.final_result = "Task cancelled by user"
        mock_cancelled.created_at = datetime.now(UTC)
        mock_cancelled.updated_at = datetime.now(UTC)
        mock_cancelled.retry_count = 0

        with (
            patch.object(
                task_service.task_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_task,
            patch.object(
                task_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_session,
            patch.object(
                task_service.task_repo,
                "update",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            mock_get_task.return_value = mock_task
            mock_get_session.return_value = mock_session
            mock_update.return_value = mock_cancelled

            result = await task_service.cancel_task(task_id, user_id)

            assert result.status == TaskStatus.FAILED.value
            mock_cache.invalidate_task_progress.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_invalid_state_for_completed_task(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises InvalidStateError for completed task."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id
        mock_task.status = TaskStatus.COMPLETED.value

        with (
            patch.object(
                task_service.task_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_task,
            patch.object(
                task_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_session,
        ):
            mock_get_task.return_value = mock_task
            mock_get_session.return_value = mock_session

            with pytest.raises(InvalidStateError):
                await task_service.cancel_task(task_id, user_id)


class TestGetMilestone:
    """Tests for get_milestone method."""

    @pytest.mark.asyncio
    async def test_returns_milestone_details(
        self,
        task_service: TaskService,
    ) -> None:
        """Returns milestone details."""
        session_id = uuid4()
        task_id = uuid4()
        milestone_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id

        mock_milestone = MagicMock()
        mock_milestone.id = milestone_id
        mock_milestone.task_id = task_id
        mock_milestone.sequence_number = 1
        mock_milestone.title = "Test Milestone"
        mock_milestone.description = ""
        mock_milestone.complexity = "simple"
        mock_milestone.status = "passed"
        mock_milestone.selected_llm = "gpt-4"
        mock_milestone.retry_count = 0
        mock_milestone.input_tokens = 100
        mock_milestone.output_tokens = 50
        mock_milestone.cost_usd = 0.005
        mock_milestone.created_at = datetime.now(UTC)
        mock_milestone.worker_output = "Output"
        mock_milestone.qa_result = None
        mock_milestone.acceptance_criteria = None

        with (
            patch.object(
                task_service.milestone_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_milestone,
            patch.object(
                task_service.task_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_task,
            patch.object(
                task_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_session,
        ):
            mock_get_milestone.return_value = mock_milestone
            mock_get_task.return_value = mock_task
            mock_get_session.return_value = mock_session

            result = await task_service.get_milestone(milestone_id, user_id)

            assert result.id == milestone_id

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_milestone(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises NotFoundError when milestone doesn't exist."""
        milestone_id = uuid4()
        user_id = "user-123"

        with patch.object(
            task_service.milestone_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None

            with pytest.raises(NotFoundError):
                await task_service.get_milestone(milestone_id, user_id)


class TestListMilestones:
    """Tests for list_milestones method."""

    @pytest.mark.asyncio
    async def test_returns_task_milestones(
        self,
        task_service: TaskService,
    ) -> None:
        """Returns list of milestones for a task."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id

        mock_milestones = [
            MagicMock(
                id=uuid4(),
                task_id=task_id,
                sequence_number=i,
                title=f"Milestone {i}",
                description="",
                complexity="simple",
                status="passed",
                selected_llm="gpt-4",
                retry_count=0,
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.005,
                created_at=datetime.now(UTC),
            )
            for i in range(2)
        ]

        with (
            patch.object(
                task_service.task_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_task,
            patch.object(
                task_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get_session,
            patch.object(
                task_service.milestone_repo,
                "get_by_task_id",
                new_callable=AsyncMock,
            ) as mock_get_milestones,
        ):
            mock_get_task.return_value = mock_task
            mock_get_session.return_value = mock_session
            mock_get_milestones.return_value = mock_milestones

            result = await task_service.list_milestones(task_id, user_id)

            assert len(result) == 2
