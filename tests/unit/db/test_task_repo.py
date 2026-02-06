"""Task repository tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.repository.task_repo import TaskRepository

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def task_repo(mock_session: AsyncMock) -> TaskRepository:
    """Create task repository."""
    return TaskRepository(mock_session)


class TestGetBySessionId:
    """Tests for get_by_session_id method."""

    @pytest.mark.asyncio
    async def test_returns_tasks_for_session(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns tasks for given session ID."""
        session_id = uuid4()

        mock_tasks = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tasks
        mock_session.execute.return_value = mock_result

        result = await task_repo.get_by_session_id(session_id)

        assert result == mock_tasks
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_applies_limit_and_offset(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Applies limit and offset parameters."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await task_repo.get_by_session_id(session_id, limit=10, offset=5)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_tasks(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when no tasks found."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await task_repo.get_by_session_id(session_id)

        assert result == []


class TestGetWithMilestones:
    """Tests for get_with_milestones method."""

    @pytest.mark.asyncio
    async def test_returns_task_with_milestones(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns task with eagerly loaded milestones."""
        task_id = uuid4()

        mock_task = MagicMock()
        mock_task.milestones = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute.return_value = mock_result

        result = await task_repo.get_with_milestones(task_id)

        assert result is not None
        assert result is mock_task
        assert len(result.milestones) == 2

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns None when task not found."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await task_repo.get_with_milestones(task_id)

        assert result is None


class TestGetWithSession:
    """Tests for get_with_session method."""

    @pytest.mark.asyncio
    async def test_returns_task_with_session(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns task with eagerly loaded session."""
        task_id = uuid4()

        mock_task = MagicMock()
        mock_task.session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute.return_value = mock_result

        result = await task_repo.get_with_session(task_id)

        assert result is not None
        assert result.session is not None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns None when task not found."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await task_repo.get_with_session(task_id)

        assert result is None


class TestGetPendingTasks:
    """Tests for get_pending_tasks method."""

    @pytest.mark.asyncio
    async def test_returns_pending_tasks(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns all pending tasks."""
        mock_tasks = [MagicMock(status="pending")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tasks
        mock_session.execute.return_value = mock_result

        result = await task_repo.get_pending_tasks()

        assert result == mock_tasks

    @pytest.mark.asyncio
    async def test_filters_by_session_id(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Filters pending tasks by session ID."""
        session_id = uuid4()

        mock_tasks = [MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tasks
        mock_session.execute.return_value = mock_result

        result = await task_repo.get_pending_tasks(session_id)

        assert result == mock_tasks
        mock_session.execute.assert_called_once()


class TestSaveHandoverContext:
    """Tests for save_handover_context method."""

    @pytest.mark.asyncio
    async def test_saves_handover_context(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Saves handover context for task."""
        task_id = uuid4()
        handover = "Summary of completed work"

        mock_task = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute.return_value = mock_result

        result = await task_repo.save_handover_context(task_id, handover)

        assert result is not None
        assert mock_task.handover_context == handover

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns None when task not found."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await task_repo.save_handover_context(task_id, "context")

        assert result is None


class TestGetPreviousTaskHandover:
    """Tests for get_previous_task_handover method."""

    @pytest.mark.asyncio
    async def test_returns_handover_from_previous_task(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns handover context from previous completed task."""
        session_id = uuid4()
        expected_handover = "Previous task summary"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_handover
        mock_session.execute.return_value = mock_result

        result = await task_repo.get_previous_task_handover(session_id)

        assert result == expected_handover

    @pytest.mark.asyncio
    async def test_returns_none_when_no_previous_task(
        self,
        task_repo: TaskRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns None when no previous completed task."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await task_repo.get_previous_task_handover(session_id)

        assert result is None
