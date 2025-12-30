"""Milestone repository tests."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.repository.milestone_repo import MilestoneRepository

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def milestone_repo(mock_session: AsyncMock) -> MilestoneRepository:
    """Create milestone repository."""
    return MilestoneRepository(mock_session)


class TestGetByTaskId:
    """Tests for get_by_task_id method."""

    @pytest.mark.asyncio
    async def test_returns_milestones_for_task(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns milestones for given task."""
        task_id = uuid4()

        mock_milestones = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_milestones
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.get_by_task_id(task_id)

        assert result == mock_milestones
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_milestones(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when task has no milestones."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.get_by_task_id(task_id)

        assert result == []


class TestGetPendingMilestones:
    """Tests for get_pending_milestones method."""

    @pytest.mark.asyncio
    async def test_returns_pending_milestones(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns only pending milestones."""
        task_id = uuid4()

        mock_milestones = [MagicMock(status="pending")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_milestones
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.get_pending_milestones(task_id)

        assert result == mock_milestones

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_complete(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when all milestones are completed."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.get_pending_milestones(task_id)

        assert result == []


class TestGetNextMilestone:
    """Tests for get_next_milestone method."""

    @pytest.mark.asyncio
    async def test_returns_next_pending_milestone(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns next pending milestone."""
        task_id = uuid4()

        mock_milestone = MagicMock(status="pending", sequence_number=2)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_milestone
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.get_next_milestone(task_id)

        assert result is mock_milestone

    @pytest.mark.asyncio
    async def test_returns_none_when_all_complete(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns None when all milestones are completed."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.get_next_milestone(task_id)

        assert result is None


class TestIncrementRetryCount:
    """Tests for increment_retry_count method."""

    @pytest.mark.asyncio
    async def test_increments_retry_count(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Increments and returns retry count."""
        milestone_id = uuid4()
        mock_milestone = MagicMock()
        mock_milestone.retry_count = 0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_milestone
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.increment_retry_count(milestone_id)

        assert result == 1
        assert mock_milestone.retry_count == 1
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_zero_when_not_found(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns 0 when milestone not found."""
        milestone_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.increment_retry_count(milestone_id)

        assert result == 0


class TestUpdateLlmUsage:
    """Tests for update_llm_usage method."""

    @pytest.mark.asyncio
    async def test_updates_llm_usage(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Updates LLM usage statistics."""
        milestone_id = uuid4()
        mock_milestone = MagicMock()
        mock_milestone.input_tokens = 100
        mock_milestone.output_tokens = 50
        mock_milestone.cost_usd = Decimal("0.005")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_milestone
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.update_llm_usage(milestone_id, 50, 25, Decimal("0.003"))

        assert result is mock_milestone
        assert mock_milestone.input_tokens == 150
        assert mock_milestone.output_tokens == 75
        assert mock_milestone.cost_usd == Decimal("0.008")
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns None when milestone not found."""
        milestone_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.update_llm_usage(milestone_id, 50, 25, Decimal("0.003"))

        assert result is None


class TestGetFailedMilestones:
    """Tests for get_failed_milestones method."""

    @pytest.mark.asyncio
    async def test_returns_failed_milestones(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns all failed milestones for a task."""
        task_id = uuid4()

        mock_milestones = [MagicMock(status="failed"), MagicMock(status="failed")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_milestones
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.get_failed_milestones(task_id)

        assert result == mock_milestones

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_failures(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when no milestones have failed."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.get_failed_milestones(task_id)

        assert result == []


class TestGetMilestonesByComplexity:
    """Tests for get_milestones_by_complexity method."""

    @pytest.mark.asyncio
    async def test_returns_milestones_by_complexity(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns milestones filtered by complexity."""
        mock_milestones = [MagicMock(complexity="simple")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_milestones
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.get_milestones_by_complexity("simple")

        assert result == mock_milestones

    @pytest.mark.asyncio
    async def test_applies_limit(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Applies limit parameter."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await milestone_repo.get_milestones_by_complexity("complex", limit=50)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_matches(
        self,
        milestone_repo: MilestoneRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when no milestones match complexity."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await milestone_repo.get_milestones_by_complexity("context_heavy")

        assert result == []
