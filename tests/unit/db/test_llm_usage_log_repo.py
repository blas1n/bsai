"""LLM usage log repository tests."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.repository.llm_usage_log_repo import LLMUsageLogRepository

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def usage_repo(mock_session: AsyncMock) -> LLMUsageLogRepository:
    """Create LLM usage log repository."""
    return LLMUsageLogRepository(mock_session)


class TestGetBySession:
    """Tests for get_by_session method."""

    @pytest.mark.asyncio
    async def test_returns_logs_for_session(
        self,
        usage_repo: LLMUsageLogRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns usage logs for given session."""
        session_id = uuid4()

        mock_logs = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_logs
        mock_session.execute.return_value = mock_result

        result = await usage_repo.get_by_session(session_id)

        assert result == mock_logs
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_applies_limit(
        self,
        usage_repo: LLMUsageLogRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Applies limit parameter."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await usage_repo.get_by_session(session_id, limit=50)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_logs(
        self,
        usage_repo: LLMUsageLogRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when no logs found."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await usage_repo.get_by_session(session_id)

        assert result == []


class TestGetTotalCost:
    """Tests for get_total_cost method."""

    @pytest.mark.asyncio
    async def test_returns_total_cost(
        self,
        usage_repo: LLMUsageLogRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns sum of costs for session."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = Decimal("1.5")
        mock_session.execute.return_value = mock_result

        result = await usage_repo.get_total_cost(session_id)

        assert result == Decimal("1.5")

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_logs(
        self,
        usage_repo: LLMUsageLogRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns zero when no logs found."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await usage_repo.get_total_cost(session_id)

        assert result == Decimal("0.0")


class TestGetByAgentType:
    """Tests for get_by_agent_type method."""

    @pytest.mark.asyncio
    async def test_returns_logs_by_agent_type(
        self,
        usage_repo: LLMUsageLogRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns logs for given agent type."""
        mock_logs = [MagicMock(agent_type="conductor")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_logs
        mock_session.execute.return_value = mock_result

        result = await usage_repo.get_by_agent_type("conductor")

        assert result == mock_logs

    @pytest.mark.asyncio
    async def test_applies_limit(
        self,
        usage_repo: LLMUsageLogRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Applies limit parameter."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await usage_repo.get_by_agent_type("worker", limit=25)

        mock_session.execute.assert_called_once()


class TestGetByMilestone:
    """Tests for get_by_milestone method."""

    @pytest.mark.asyncio
    async def test_returns_logs_for_milestone(
        self,
        usage_repo: LLMUsageLogRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns usage logs for given milestone."""
        milestone_id = uuid4()

        mock_logs = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_logs
        mock_session.execute.return_value = mock_result

        result = await usage_repo.get_by_milestone(milestone_id)

        assert result == mock_logs
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_logs(
        self,
        usage_repo: LLMUsageLogRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when no logs found."""
        milestone_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await usage_repo.get_by_milestone(milestone_id)

        assert result == []
