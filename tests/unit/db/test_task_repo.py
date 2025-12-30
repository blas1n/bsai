"""Task repository tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
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


class TestUpdateStatus:
    """Tests for update_status method."""

    @pytest.mark.asyncio
    async def test_updates_task_status(
        self,
        task_repo: TaskRepository,
    ) -> None:
        """Updates task status."""
        task_id = uuid4()

        with patch.object(
            task_repo,
            "update",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_task = MagicMock()
            mock_update.return_value = mock_task

            result = await task_repo.update_status(task_id, "in_progress")

            assert result is mock_task
            mock_update.assert_called_once_with(task_id, status="in_progress")


class TestCompleteTask:
    """Tests for complete_task method."""

    @pytest.mark.asyncio
    async def test_marks_task_completed(
        self,
        task_repo: TaskRepository,
    ) -> None:
        """Marks task as completed with result."""
        task_id = uuid4()

        with patch.object(
            task_repo,
            "update",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_task = MagicMock()
            mock_update.return_value = mock_task

            result = await task_repo.complete_task(task_id, "Task completed successfully")

            assert result is mock_task
            mock_update.assert_called_once_with(
                task_id,
                status="completed",
                final_result="Task completed successfully",
            )


class TestFailTask:
    """Tests for fail_task method."""

    @pytest.mark.asyncio
    async def test_marks_task_failed(
        self,
        task_repo: TaskRepository,
    ) -> None:
        """Marks task as failed with error message."""
        task_id = uuid4()

        with patch.object(
            task_repo,
            "update",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_task = MagicMock()
            mock_update.return_value = mock_task

            result = await task_repo.fail_task(task_id, "Something went wrong")

            assert result is mock_task
            mock_update.assert_called_once_with(
                task_id,
                status="failed",
                final_result="Something went wrong",
            )
