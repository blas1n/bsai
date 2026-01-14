"""Task service tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.api.exceptions import AccessDeniedError, InvalidStateError, NotFoundError
from agent.api.schemas import TaskCreate
from agent.api.services.task_service import TaskService
from agent.db.models.enums import SessionStatus, TaskStatus
from agent.services import BreakpointService

if TYPE_CHECKING:
    pass

from agent.graph.state import AgentState


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
def mock_event_bus() -> MagicMock:
    """Create mock event bus."""
    event_bus = MagicMock()
    event_bus.emit = AsyncMock()
    return event_bus


@pytest.fixture
def mock_breakpoint_service() -> BreakpointService:
    """Create real breakpoint service instance.

    BreakpointService is a simple in-memory state manager with no external dependencies,
    so using a real instance is cleaner and avoids MagicMock coroutine warnings.
    """
    return BreakpointService()


@pytest.fixture
def mock_ws_manager() -> MagicMock:
    """Create mock WebSocket connection manager."""
    manager = MagicMock()
    manager.broadcast_to_session = AsyncMock()
    return manager


@pytest.fixture
def task_service(
    mock_db: AsyncMock,
    mock_cache: MagicMock,
    mock_event_bus: MagicMock,
    mock_ws_manager: MagicMock,
    mock_breakpoint_service: MagicMock,
) -> TaskService:
    """Create task service with mocked dependencies."""
    return TaskService(
        mock_db,
        mock_cache,
        mock_event_bus,
        mock_ws_manager,
        mock_breakpoint_service,
    )


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
            # Prevent "coroutine was never awaited" warning by closing the coroutine
            mock_create_task.side_effect = lambda coro: coro.close() or MagicMock()

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
            patch.object(
                task_service.agent_step_repo,
                "get_steps_by_task",
                new_callable=AsyncMock,
            ) as mock_agent_steps,
            patch.object(
                task_service.agent_step_repo,
                "get_cost_breakdown_by_agent",
                new_callable=AsyncMock,
            ) as mock_cost_breakdown,
        ):
            mock_get_task.return_value = mock_task
            mock_get_session.return_value = mock_session
            mock_milestones.return_value = []
            mock_agent_steps.return_value = []
            mock_cost_breakdown.return_value = {}

            result = await task_service.get_task(task_id, user_id)

            assert result.id == task_id
            assert result.milestones == []
            assert result.agent_steps == []
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


class TestResumeTask:
    """Tests for resume_task method."""

    @pytest.mark.asyncio
    async def test_resumes_in_progress_task(
        self,
        task_service: TaskService,
    ) -> None:
        """Resumes an in-progress task."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id
        mock_task.original_request = "Test"
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
            patch("asyncio.create_task") as mock_create_task,
        ):
            mock_get_task.return_value = mock_task
            mock_get_session.return_value = mock_session
            mock_create_task.side_effect = lambda coro: coro.close() or MagicMock()

            result = await task_service.resume_task(task_id, user_id)

            assert result.id == task_id
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_resumes_with_user_input(
        self,
        task_service: TaskService,
    ) -> None:
        """Resumes task with user-provided input."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id
        mock_task.original_request = "Test"
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
            patch("asyncio.create_task") as mock_create_task,
        ):
            mock_get_task.return_value = mock_task
            mock_get_session.return_value = mock_session
            mock_create_task.side_effect = lambda coro: coro.close() or MagicMock()

            result = await task_service.resume_task(task_id, user_id, user_input="Modified output")

            assert result.id == task_id

    @pytest.mark.asyncio
    async def test_raises_invalid_state_for_completed_task(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises InvalidStateError when resuming completed task."""
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
                await task_service.resume_task(task_id, user_id)


class TestRejectTask:
    """Tests for reject_task method."""

    @pytest.mark.asyncio
    async def test_rejects_in_progress_task(
        self,
        task_service: TaskService,
        mock_cache: MagicMock,
    ) -> None:
        """Rejects an in-progress task."""
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

        mock_rejected = MagicMock()
        mock_rejected.id = task_id
        mock_rejected.session_id = session_id
        mock_rejected.original_request = "Test"
        mock_rejected.status = TaskStatus.FAILED.value
        mock_rejected.final_result = "Task rejected by user"
        mock_rejected.created_at = datetime.now(UTC)
        mock_rejected.updated_at = datetime.now(UTC)
        mock_rejected.retry_count = 0

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
            mock_update.return_value = mock_rejected

            result = await task_service.reject_task(task_id, user_id)

            assert result.status == TaskStatus.FAILED.value
            mock_cache.invalidate_task_progress.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_with_reason(
        self,
        task_service: TaskService,
        mock_cache: MagicMock,
    ) -> None:
        """Rejects task with optional reason."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"
        reason = "Output quality is not acceptable"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id
        mock_task.status = TaskStatus.IN_PROGRESS.value

        mock_rejected = MagicMock()
        mock_rejected.id = task_id
        mock_rejected.session_id = session_id
        mock_rejected.original_request = "Test"
        mock_rejected.status = TaskStatus.FAILED.value
        mock_rejected.final_result = f"Task rejected by user: {reason}"
        mock_rejected.created_at = datetime.now(UTC)
        mock_rejected.updated_at = datetime.now(UTC)
        mock_rejected.retry_count = 0

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
            mock_update.return_value = mock_rejected

            result = await task_service.reject_task(task_id, user_id, reason=reason)

            assert result.final_result is not None and reason in result.final_result

    @pytest.mark.asyncio
    async def test_broadcasts_failure_via_websocket(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
    ) -> None:
        """Broadcasts failure notification via WebSocket."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"

        mock_event_bus = MagicMock()
        mock_event_bus.emit = AsyncMock()

        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_to_session = AsyncMock()

        breakpoint_service = BreakpointService()
        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, breakpoint_service
        )

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id
        mock_task.status = TaskStatus.IN_PROGRESS.value

        mock_rejected = MagicMock()
        mock_rejected.id = task_id
        mock_rejected.session_id = session_id
        mock_rejected.original_request = "Test"
        mock_rejected.status = TaskStatus.FAILED.value
        mock_rejected.final_result = "Task rejected by user"
        mock_rejected.created_at = datetime.now(UTC)
        mock_rejected.updated_at = datetime.now(UTC)
        mock_rejected.retry_count = 0

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
            mock_update.return_value = mock_rejected

            await task_service.reject_task(task_id, user_id)

            mock_ws_manager.broadcast_to_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_invalid_state_for_pending_task(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises InvalidStateError when rejecting pending task."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id
        mock_task.status = TaskStatus.PENDING.value

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
                await task_service.reject_task(task_id, user_id)


class TestGetTaskForUser:
    """Tests for _get_task_for_user helper method."""

    @pytest.mark.asyncio
    async def test_returns_task_when_user_owns_session(
        self,
        task_service: TaskService,
    ) -> None:
        """Returns task when user owns the session."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id

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

            result = await task_service._get_task_for_user(task_id, user_id)

            assert result == mock_task

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
                await task_service._get_task_for_user(task_id, user_id)

    @pytest.mark.asyncio
    async def test_raises_access_denied_for_other_user(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises AccessDeniedError when user doesn't own session."""
        session_id = uuid4()
        task_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = "other-user"

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id

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

            with pytest.raises(AccessDeniedError):
                await task_service._get_task_for_user(task_id, "user-123")

    @pytest.mark.asyncio
    async def test_raises_access_denied_for_missing_session(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises AccessDeniedError when session doesn't exist."""
        session_id = uuid4()
        task_id = uuid4()

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.session_id = session_id

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
            mock_get_session.return_value = None

            with pytest.raises(AccessDeniedError):
                await task_service._get_task_for_user(task_id, "user-123")


class TestListTasksWithFiltering:
    """Tests for list_tasks filtering and pagination."""

    @pytest.mark.asyncio
    async def test_filters_by_status(
        self,
        task_service: TaskService,
    ) -> None:
        """Filters tasks by status."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        mock_tasks = [
            MagicMock(
                id=uuid4(),
                session_id=session_id,
                original_request="Request",
                status=TaskStatus.COMPLETED.value,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                final_result="Result",
                retry_count=0,
            ),
            MagicMock(
                id=uuid4(),
                session_id=session_id,
                original_request="Request 2",
                status=TaskStatus.IN_PROGRESS.value,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                final_result=None,
                retry_count=0,
            ),
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

            result = await task_service.list_tasks(session_id, user_id, status=TaskStatus.COMPLETED)

            assert len(result.items) == 1
            assert result.items[0].status == TaskStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_detects_has_more(
        self,
        task_service: TaskService,
    ) -> None:
        """Detects when there are more results."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id

        # Create limit+1 tasks to trigger has_more
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
            for i in range(3)  # limit=2, so 3 means has_more=True
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

            result = await task_service.list_tasks(session_id, user_id, limit=2)

            assert len(result.items) == 2
            assert result.has_more is True


class TestGetTaskWithCostBreakdown:
    """Tests for get_task with cost breakdown."""

    @pytest.mark.asyncio
    async def test_returns_task_with_cost_breakdown(
        self,
        task_service: TaskService,
    ) -> None:
        """Returns task details with cost breakdown by agent."""
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
        mock_task.status = TaskStatus.COMPLETED.value
        mock_task.created_at = datetime.now(UTC)
        mock_task.updated_at = datetime.now(UTC)
        mock_task.final_result = "Result"
        mock_task.retry_count = 0

        mock_cost_breakdown = {
            "worker": {
                "total_cost_usd": Decimal("0.05"),
                "total_input_tokens": 1000,
                "total_output_tokens": 500,
                "step_count": 2,
                "total_duration_ms": 5000,
            },
            "qa": {
                "total_cost_usd": Decimal("0.02"),
                "total_input_tokens": 500,
                "total_output_tokens": 200,
                "step_count": 1,
                "total_duration_ms": 2000,
            },
        }

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
            patch.object(
                task_service.agent_step_repo,
                "get_steps_by_task",
                new_callable=AsyncMock,
            ) as mock_agent_steps,
            patch.object(
                task_service.agent_step_repo,
                "get_cost_breakdown_by_agent",
                new_callable=AsyncMock,
            ) as mock_cost,
        ):
            mock_get_task.return_value = mock_task
            mock_get_session.return_value = mock_session
            mock_milestones.return_value = []
            mock_agent_steps.return_value = []
            mock_cost.return_value = mock_cost_breakdown

            result = await task_service.get_task(task_id, user_id)

            assert result.cost_breakdown is not None
            assert "worker" in result.cost_breakdown
            assert result.cost_breakdown["worker"]["total_cost_usd"] == "0.05"

    @pytest.mark.asyncio
    async def test_returns_task_with_milestones_progress(
        self,
        task_service: TaskService,
    ) -> None:
        """Returns task with correct progress calculation."""
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

        mock_milestones = [
            MagicMock(
                id=uuid4(),
                task_id=task_id,
                sequence_number=1,
                title="Milestone 1",
                description="",
                complexity="simple",
                status="passed",
                selected_llm="gpt-4",
                retry_count=0,
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.005,
                created_at=datetime.now(UTC),
            ),
            MagicMock(
                id=uuid4(),
                task_id=task_id,
                sequence_number=2,
                title="Milestone 2",
                description="",
                complexity="simple",
                status="pending",
                selected_llm="gpt-4",
                retry_count=0,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0,
                created_at=datetime.now(UTC),
            ),
        ]

        mock_agent_steps = [
            MagicMock(
                id=uuid4(),
                task_id=task_id,
                milestone_id=None,
                agent_type="worker",
                status="completed",
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                duration_ms=1000,
                input_summary="Test input",
                output_summary="Test output",
                input_tokens=100,
                output_tokens=50,
                cost_usd=Decimal("0.005"),
                error_message=None,
            ),
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
            patch.object(
                task_service.agent_step_repo,
                "get_steps_by_task",
                new_callable=AsyncMock,
            ) as mock_get_steps,
            patch.object(
                task_service.agent_step_repo,
                "get_cost_breakdown_by_agent",
                new_callable=AsyncMock,
            ) as mock_cost,
        ):
            mock_get_task.return_value = mock_task
            mock_get_session.return_value = mock_session
            mock_get_milestones.return_value = mock_milestones
            mock_get_steps.return_value = mock_agent_steps
            mock_cost.return_value = {}

            result = await task_service.get_task(task_id, user_id)

            assert result.progress == 0.5  # 1 passed out of 2
            assert result.total_duration_ms == 1000
            assert len(result.milestones) == 2
            assert len(result.agent_steps) == 1


class TestListTasksAccessDenied:
    """Tests for list_tasks access denied cases."""

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_session(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises NotFoundError when session doesn't exist."""
        session_id = uuid4()
        user_id = "user-123"

        with patch.object(
            task_service.session_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None

            with pytest.raises(NotFoundError):
                await task_service.list_tasks(session_id, user_id)

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

        with patch.object(
            task_service.session_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_session

            with pytest.raises(AccessDeniedError):
                await task_service.list_tasks(session_id, "user-123")


class TestCancelTaskUpdateFailure:
    """Tests for cancel_task update failure cases."""

    @pytest.mark.asyncio
    async def test_raises_not_found_when_update_fails(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises NotFoundError when update returns None."""
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
            mock_update.return_value = None

            with pytest.raises(NotFoundError):
                await task_service.cancel_task(task_id, user_id)


class TestRejectTaskUpdateFailure:
    """Tests for reject_task update failure cases."""

    @pytest.mark.asyncio
    async def test_raises_not_found_when_update_fails(
        self,
        task_service: TaskService,
    ) -> None:
        """Raises NotFoundError when update returns None."""
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
            mock_update.return_value = None

            with pytest.raises(NotFoundError):
                await task_service.reject_task(task_id, user_id)


class TestSaveContextToCache:
    """Tests for _save_context_to_cache method."""

    @pytest.mark.asyncio
    async def test_saves_context_messages(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_ws_manager: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Saves context messages to cache."""
        mock_cache.cache_context = AsyncMock()
        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()

        # Create mock ChatMessage objects
        mock_msg = MagicMock()
        mock_msg.role = "user"
        mock_msg.content = "Test message"

        final_state = AgentState(
            session_id=session_id,
            task_id=uuid4(),
            user_id="test-user",
            original_request="Test request",
            context_messages=[mock_msg],
            context_summary="Summary of conversation",
            current_context_tokens=500,
        )

        await task_service._save_context_to_cache(session_id, final_state)

        mock_cache.cache_context.assert_called_once()
        call_kwargs = mock_cache.cache_context.call_args[1]
        assert call_kwargs["session_id"] == session_id
        assert call_kwargs["token_count"] == 500
        assert call_kwargs["summary"] == "Summary of conversation"

    @pytest.mark.asyncio
    async def test_skips_empty_context(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_ws_manager: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Skips caching when no context messages."""
        mock_cache.cache_context = AsyncMock()
        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        final_state = AgentState(
            session_id=session_id,
            task_id=uuid4(),
            user_id="test-user",
            original_request="Test request",
            context_messages=[],
            context_summary=None,
            current_context_tokens=0,
        )

        await task_service._save_context_to_cache(session_id, final_state)

        mock_cache.cache_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_missing_token_count(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_ws_manager: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Skips caching when token count is missing."""
        mock_cache.cache_context = AsyncMock()
        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()

        mock_msg = MagicMock()
        mock_msg.role = "user"
        mock_msg.content = "Test"

        # Use cast for this edge case test where current_context_tokens is None
        # (which shouldn't happen in normal flow but tests defensive coding)
        final_state = cast(
            AgentState,
            {
                "session_id": session_id,
                "task_id": uuid4(),
                "user_id": "test-user",
                "original_request": "Test request",
                "context_messages": [mock_msg],
                "context_summary": None,
                "current_context_tokens": None,
            },
        )

        await task_service._save_context_to_cache(session_id, final_state)

        mock_cache.cache_context.assert_not_called()


class TestExecuteTask:
    """Tests for _execute_task method."""

    @pytest.mark.asyncio
    async def test_executes_task_successfully(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Executes task and updates status on success."""
        mock_event_bus = MagicMock()
        mock_event_bus.emit = AsyncMock()

        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_to_session = AsyncMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.total_input_tokens = 0
        mock_session.total_output_tokens = 0
        mock_session.total_cost_usd = Decimal("0")

        mock_result = MagicMock()
        mock_result.state = {
            "task_status": TaskStatus.COMPLETED,
            "final_response": "Task completed successfully",
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_cost_usd": "0.01",
            "context_messages": [],
        }
        mock_result.interrupted = False

        async def mock_get_db_session():
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
            mock_session_repo.update = AsyncMock()

            mock_task_repo = MagicMock()
            mock_task_repo.update = AsyncMock()

            mock_milestone_repo = MagicMock()
            mock_milestone_repo.get_by_session_id = AsyncMock(return_value=[])

            db = AsyncMock()
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch("agent.api.services.task_service.TaskRepository") as mock_task_repo_class,
            patch("agent.api.services.task_service.SessionRepository") as mock_session_repo_class,
            patch(
                "agent.api.services.task_service.MilestoneRepository"
            ) as mock_milestone_repo_class,
            patch.object(
                task_service,
                "_save_context_to_cache",
                new_callable=AsyncMock,
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            mock_task_repo = MagicMock()
            mock_task_repo.update = AsyncMock()
            mock_task_repo_class.return_value = mock_task_repo

            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
            mock_session_repo.update = AsyncMock()
            mock_session_repo_class.return_value = mock_session_repo

            mock_milestone_repo = MagicMock()
            mock_milestone_repo.get_by_session_id = AsyncMock(return_value=[])
            mock_milestone_repo_class.return_value = mock_milestone_repo

            await task_service._execute_task(
                session_id=session_id,
                task_id=task_id,
                original_request="Test request",
                max_context_tokens=4000,
                stream=True,
            )

            # Verify task started notification was sent
            assert mock_ws_manager.broadcast_to_session.call_count >= 1

    @pytest.mark.asyncio
    async def test_handles_workflow_interruption(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_ws_manager: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Handles workflow interruption at breakpoint."""
        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.state = {}
        mock_result.interrupted = True
        mock_result.interrupt_node = "worker"

        async def mock_get_db_session():
            db = AsyncMock()
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch("agent.api.services.task_service.TaskRepository") as mock_task_repo_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            mock_task_repo = MagicMock()
            mock_task_repo.update = AsyncMock()
            mock_task_repo_class.return_value = mock_task_repo

            # Should return early without updating to completed
            await task_service._execute_task(
                session_id=session_id,
                task_id=task_id,
                original_request="Test request",
                max_context_tokens=4000,
                stream=False,
                breakpoint_enabled=True,
            )

            # Workflow runner should have been called
            mock_runner.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_task_failure(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_ws_manager: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Handles task failure from workflow."""
        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.total_input_tokens = 0
        mock_session.total_output_tokens = 0
        mock_session.total_cost_usd = Decimal("0")

        mock_result = MagicMock()
        mock_result.state = {
            "task_status": TaskStatus.FAILED,
            "error": "Max retries exceeded",
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_cost_usd": "0.01",
        }
        mock_result.interrupted = False

        async def mock_get_db_session():
            db = AsyncMock()
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch("agent.api.services.task_service.TaskRepository") as mock_task_repo_class,
            patch("agent.api.services.task_service.SessionRepository") as mock_session_repo_class,
            patch.object(
                task_service,
                "_handle_task_failure",
                new_callable=AsyncMock,
            ) as mock_handle_failure,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            mock_task_repo = MagicMock()
            mock_task_repo.update = AsyncMock()
            mock_task_repo_class.return_value = mock_task_repo

            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
            mock_session_repo_class.return_value = mock_session_repo

            await task_service._execute_task(
                session_id=session_id,
                task_id=task_id,
                original_request="Test request",
                max_context_tokens=4000,
                stream=False,
            )

            mock_handle_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_execution_exception(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Handles exception during execution."""
        mock_event_bus = MagicMock()
        mock_event_bus.emit = AsyncMock()

        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_to_session = AsyncMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        async def mock_get_db_session():
            db = AsyncMock()
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch("agent.api.services.task_service.TaskRepository") as mock_task_repo_class,
            patch(
                "agent.api.services.task_service.MilestoneRepository"
            ) as mock_milestone_repo_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(side_effect=Exception("Workflow error"))
            mock_runner_class.return_value = mock_runner

            mock_task_repo = MagicMock()
            mock_task_repo.update = AsyncMock()
            mock_task_repo_class.return_value = mock_task_repo

            mock_milestone_repo = MagicMock()
            mock_milestone_repo.get_by_session_id = AsyncMock(return_value=[])
            mock_milestone_repo_class.return_value = mock_milestone_repo

            await task_service._execute_task(
                session_id=session_id,
                task_id=task_id,
                original_request="Test request",
                max_context_tokens=4000,
                stream=True,
            )

            # Should notify failure via websocket
            assert mock_ws_manager.broadcast_to_session.call_count >= 1

    @pytest.mark.asyncio
    async def test_uses_fallback_result_from_milestone(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_ws_manager: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Uses fallback result from last milestone when final_response is empty."""
        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.total_input_tokens = 0
        mock_session.total_output_tokens = 0
        mock_session.total_cost_usd = Decimal("0")

        mock_result = MagicMock()
        mock_result.state = {
            "task_status": TaskStatus.COMPLETED,
            "final_response": "",  # Empty response
            "milestones": [
                {"worker_output": "Milestone 1 output"},
                {"worker_output": "Last milestone output"},
            ],
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_cost_usd": "0.01",
            "context_messages": [],
        }
        mock_result.interrupted = False

        async def mock_get_db_session():
            db = AsyncMock()
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch("agent.api.services.task_service.TaskRepository") as mock_task_repo_class,
            patch("agent.api.services.task_service.SessionRepository") as mock_session_repo_class,
            patch.object(
                task_service,
                "_save_context_to_cache",
                new_callable=AsyncMock,
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            mock_task_repo = MagicMock()
            mock_task_repo.update = AsyncMock()
            mock_task_repo_class.return_value = mock_task_repo

            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
            mock_session_repo.update = AsyncMock()
            mock_session_repo_class.return_value = mock_session_repo

            await task_service._execute_task(
                session_id=session_id,
                task_id=task_id,
                original_request="Test request",
                max_context_tokens=4000,
                stream=False,
            )

            # Verify task repo update was called with fallback result
            mock_task_repo.update.assert_called()


class TestHandleTaskFailure:
    """Tests for _handle_task_failure method."""

    @pytest.mark.asyncio
    async def test_updates_task_status_on_failure(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_ws_manager: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Updates task status to FAILED."""
        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.total_input_tokens = 0
        mock_session.total_output_tokens = 0
        mock_session.total_cost_usd = Decimal("0")

        final_state: AgentState = cast(
            AgentState,
            {
                "error": "Task failed due to max retries",
                "current_milestone_index": 1,
            },
        )

        mock_task_repo = MagicMock()
        mock_task_repo.update = AsyncMock()

        mock_session_repo = MagicMock()
        mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
        mock_session_repo.update = AsyncMock()

        with (
            patch(
                "agent.api.services.task_service.TaskRepository",
                return_value=mock_task_repo,
            ),
            patch(
                "agent.api.services.task_service.SessionRepository",
                return_value=mock_session_repo,
            ),
        ):
            await task_service._handle_task_failure(
                db_session=mock_db,
                session_id=session_id,
                task_id=task_id,
                final_state=final_state,
                total_input_tokens=100,
                total_output_tokens=50,
                total_cost=Decimal("0.01"),
                stream=False,
            )

            mock_task_repo.update.assert_called_once_with(
                task_id,
                status=TaskStatus.FAILED.value,
                final_result="Task failed due to max retries",
            )

    @pytest.mark.asyncio
    async def test_updates_session_totals_on_failure(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_ws_manager: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Updates session totals even on failure."""
        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.total_input_tokens = 500
        mock_session.total_output_tokens = 200
        mock_session.total_cost_usd = Decimal("0.05")

        final_state: AgentState = cast(
            AgentState,
            {
                "error": "Task failed",
            },
        )

        mock_task_repo = MagicMock()
        mock_task_repo.update = AsyncMock()

        mock_session_repo = MagicMock()
        mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
        mock_session_repo.update = AsyncMock()

        with (
            patch(
                "agent.api.services.task_service.TaskRepository",
                return_value=mock_task_repo,
            ),
            patch(
                "agent.api.services.task_service.SessionRepository",
                return_value=mock_session_repo,
            ),
        ):
            await task_service._handle_task_failure(
                db_session=mock_db,
                session_id=session_id,
                task_id=task_id,
                final_state=final_state,
                total_input_tokens=100,
                total_output_tokens=50,
                total_cost=Decimal("0.01"),
                stream=False,
            )

            mock_session_repo.update.assert_called_once_with(
                session_id,
                total_input_tokens=600,  # 500 + 100
                total_output_tokens=250,  # 200 + 50
                total_cost_usd=Decimal("0.06"),  # 0.05 + 0.01
            )

    @pytest.mark.asyncio
    async def test_broadcasts_failure_via_websocket(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Broadcasts failure notification via WebSocket when streaming."""
        mock_event_bus = MagicMock()
        mock_event_bus.emit = AsyncMock()

        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_to_session = AsyncMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.total_input_tokens = 0
        mock_session.total_output_tokens = 0
        mock_session.total_cost_usd = Decimal("0")

        final_state: AgentState = cast(
            AgentState,
            {
                "error": "Task failed",
                "current_milestone_index": 2,
            },
        )

        mock_task_repo = MagicMock()
        mock_task_repo.update = AsyncMock()

        mock_session_repo = MagicMock()
        mock_session_repo.get_by_id = AsyncMock(return_value=mock_session)
        mock_session_repo.update = AsyncMock()

        with (
            patch(
                "agent.api.services.task_service.TaskRepository",
                return_value=mock_task_repo,
            ),
            patch(
                "agent.api.services.task_service.SessionRepository",
                return_value=mock_session_repo,
            ),
        ):
            await task_service._handle_task_failure(
                db_session=mock_db,
                session_id=session_id,
                task_id=task_id,
                final_state=final_state,
                total_input_tokens=100,
                total_output_tokens=50,
                total_cost=Decimal("0.01"),
                stream=True,
            )

            mock_ws_manager.broadcast_to_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_default_error_message(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_ws_manager: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Uses default error message when error is not in state."""
        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        final_state: AgentState = cast(AgentState, {})  # No error in state

        mock_task_repo = MagicMock()
        mock_task_repo.update = AsyncMock()

        mock_session_repo = MagicMock()
        mock_session_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(
                "agent.api.services.task_service.TaskRepository",
                return_value=mock_task_repo,
            ),
            patch(
                "agent.api.services.task_service.SessionRepository",
                return_value=mock_session_repo,
            ),
        ):
            await task_service._handle_task_failure(
                db_session=mock_db,
                session_id=session_id,
                task_id=task_id,
                final_state=final_state,
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost=Decimal("0"),
                stream=False,
            )

            mock_task_repo.update.assert_called_once_with(
                task_id,
                status=TaskStatus.FAILED.value,
                final_result="Task failed after maximum retry attempts",
            )


class TestResumeTaskExecution:
    """Tests for _resume_task_execution method."""

    @pytest.mark.asyncio
    async def test_resumes_workflow_successfully(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Resumes workflow and completes successfully."""
        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_to_session = AsyncMock()
        mock_breakpoint_service = MagicMock()
        mock_breakpoint_service.clear_paused_at = MagicMock()
        mock_breakpoint_service.cleanup_task = MagicMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.state = {
            "task_status": TaskStatus.COMPLETED,
            "final_response": "Resumed task completed",
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_cost_usd": "0.01",
        }
        mock_result.interrupted = False

        async def mock_get_db_session():
            db = AsyncMock()
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch("agent.api.services.task_service.TaskRepository") as mock_task_repo_class,
        ):
            mock_runner = MagicMock()
            mock_runner.resume = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            mock_task_repo = MagicMock()
            mock_task_repo.update = AsyncMock()
            mock_task_repo_class.return_value = mock_task_repo

            await task_service._resume_task_execution(
                session_id=session_id,
                task_id=task_id,
                user_input="Approved",
            )

            mock_breakpoint_service.clear_paused_at.assert_called_once_with(task_id)
            mock_runner.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_another_breakpoint_after_resume(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Handles when workflow pauses at another breakpoint after resume."""
        mock_ws_manager = MagicMock()
        mock_breakpoint_service = MagicMock()
        mock_breakpoint_service.clear_paused_at = MagicMock()
        mock_breakpoint_service.cleanup_task = MagicMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.state = {}
        mock_result.interrupted = True
        mock_result.interrupt_node = "qa"

        async def mock_get_db_session():
            db = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.resume = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            await task_service._resume_task_execution(
                session_id=session_id,
                task_id=task_id,
            )

            # Should return early without completing
            mock_runner.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_none_result(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Handles when resume returns None (no checkpoint found)."""
        mock_ws_manager = MagicMock()
        mock_breakpoint_service = MagicMock()
        mock_breakpoint_service.clear_paused_at = MagicMock()
        mock_breakpoint_service.cleanup_task = MagicMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        async def mock_get_db_session():
            db = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.resume = AsyncMock(return_value=None)
            mock_runner_class.return_value = mock_runner

            # Should handle gracefully without error
            await task_service._resume_task_execution(
                session_id=session_id,
                task_id=task_id,
            )

    @pytest.mark.asyncio
    async def test_handles_failure_after_resume(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Handles task failure after resume."""
        mock_ws_manager = MagicMock()
        mock_breakpoint_service = MagicMock()
        mock_breakpoint_service.clear_paused_at = MagicMock()
        mock_breakpoint_service.cleanup_task = MagicMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.total_input_tokens = 0
        mock_session.total_output_tokens = 0
        mock_session.total_cost_usd = Decimal("0")

        mock_result = MagicMock()
        mock_result.state = {
            "task_status": TaskStatus.FAILED,
            "error": "QA failed",
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_cost_usd": "0.01",
        }
        mock_result.interrupted = False

        async def mock_get_db_session():
            db = AsyncMock()
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch.object(
                task_service,
                "_handle_task_failure",
                new_callable=AsyncMock,
            ) as mock_handle_failure,
        ):
            mock_runner = MagicMock()
            mock_runner.resume = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            await task_service._resume_task_execution(
                session_id=session_id,
                task_id=task_id,
            )

            mock_handle_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_exception_during_resume(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Handles exception during resume."""
        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_to_session = AsyncMock()
        mock_breakpoint_service = MagicMock()
        mock_breakpoint_service.clear_paused_at = MagicMock()
        mock_breakpoint_service.cleanup_task = MagicMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_task = MagicMock()
        mock_task.session_id = session_id

        async def mock_get_db_session():
            db = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch("agent.api.services.task_service.TaskRepository") as mock_task_repo_class,
        ):
            mock_runner = MagicMock()
            mock_runner.resume = AsyncMock(side_effect=Exception("Resume error"))
            mock_runner_class.return_value = mock_runner

            mock_task_repo = MagicMock()
            mock_task_repo.get_by_id = AsyncMock(return_value=mock_task)
            mock_task_repo_class.return_value = mock_task_repo

            # Should handle gracefully
            await task_service._resume_task_execution(
                session_id=session_id,
                task_id=task_id,
            )

            # Should broadcast failure
            mock_ws_manager.broadcast_to_session.assert_called()

    @pytest.mark.asyncio
    async def test_does_not_clear_paused_state_when_rejected_with_feedback(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Does not clear paused state when rejected with feedback."""
        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_to_session = AsyncMock()
        mock_breakpoint_service = MagicMock()
        mock_breakpoint_service.clear_paused_at = MagicMock()
        mock_breakpoint_service.cleanup_task = MagicMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.state = {
            "task_status": TaskStatus.COMPLETED,
            "final_response": "Re-executed with feedback",
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_cost_usd": "0.01",
        }
        mock_result.interrupted = False

        async def mock_get_db_session():
            db = AsyncMock()
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch("agent.api.services.task_service.TaskRepository") as mock_task_repo_class,
        ):
            mock_runner = MagicMock()
            mock_runner.resume = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            mock_task_repo = MagicMock()
            mock_task_repo.update = AsyncMock()
            mock_task_repo_class.return_value = mock_task_repo

            await task_service._resume_task_execution(
                session_id=session_id,
                task_id=task_id,
                user_input="Please fix the output",
                rejected=True,
            )

            # Should NOT clear paused state when rejected with feedback
            mock_breakpoint_service.clear_paused_at.assert_not_called()

    @pytest.mark.asyncio
    async def test_clears_paused_state_when_rejected_without_feedback(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Clears paused state and cancels when rejected without feedback."""
        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_to_session = AsyncMock()
        mock_breakpoint_service = MagicMock()
        mock_breakpoint_service.clear_paused_at = MagicMock()
        mock_breakpoint_service.cleanup_task = MagicMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.state = {
            "task_status": TaskStatus.COMPLETED,
            "final_response": "Task cancelled",
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": "0",
        }
        mock_result.interrupted = False

        async def mock_get_db_session():
            db = AsyncMock()
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch("agent.api.services.task_service.TaskRepository") as mock_task_repo_class,
        ):
            mock_runner = MagicMock()
            mock_runner.resume = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            mock_task_repo = MagicMock()
            mock_task_repo.update = AsyncMock()
            mock_task_repo_class.return_value = mock_task_repo

            await task_service._resume_task_execution(
                session_id=session_id,
                task_id=task_id,
                user_input=None,
                rejected=True,
            )

            # Should clear paused state when rejected without feedback
            mock_breakpoint_service.clear_paused_at.assert_called_once_with(task_id)

    @pytest.mark.asyncio
    async def test_uses_fallback_result_from_milestone_on_resume(
        self,
        mock_db: AsyncMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Uses fallback result from milestone when final_response is empty on resume."""
        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_to_session = AsyncMock()
        mock_breakpoint_service = MagicMock()
        mock_breakpoint_service.clear_paused_at = MagicMock()
        mock_breakpoint_service.cleanup_task = MagicMock()

        task_service = TaskService(
            mock_db, mock_cache, mock_event_bus, mock_ws_manager, mock_breakpoint_service
        )

        session_id = uuid4()
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.state = {
            "task_status": TaskStatus.COMPLETED,
            "final_response": "",  # Empty
            "milestones": [{"worker_output": "Output from milestone"}],
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_cost_usd": "0.01",
        }
        mock_result.interrupted = False

        async def mock_get_db_session():
            db = AsyncMock()
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "agent.api.services.task_service.get_db_session",
                mock_get_db_session,
            ),
            patch("agent.api.services.task_service.WorkflowRunner") as mock_runner_class,
            patch("agent.api.services.task_service.TaskRepository") as mock_task_repo_class,
        ):
            mock_runner = MagicMock()
            mock_runner.resume = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            mock_task_repo = MagicMock()
            mock_task_repo.update = AsyncMock()
            mock_task_repo_class.return_value = mock_task_repo

            await task_service._resume_task_execution(
                session_id=session_id,
                task_id=task_id,
            )

            # Task repo should have been updated with milestone output
            mock_task_repo.update.assert_called()
