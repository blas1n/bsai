"""Tests for AgentStepRepository.

Note: Business logic methods (start_step, complete_step) have been moved
to AgentStepService. This file tests only the pure query methods.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from bsai.db.repository.agent_step_repo import AgentStepRepository


class TestAgentStepRepository:
    """Tests for AgentStepRepository query methods."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> AgentStepRepository:
        """Create repository with mock session."""
        return AgentStepRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_steps_by_task_returns_ordered_list(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """get_steps_by_task returns steps ordered by started_at."""
        task_id = uuid4()

        mock_steps = [
            MagicMock(id=uuid4(), agent_type="architect", status="completed"),
            MagicMock(id=uuid4(), agent_type="worker", status="completed"),
            MagicMock(id=uuid4(), agent_type="qa", status="completed"),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_steps
        mock_session.execute.return_value = mock_result

        result = await repository.get_steps_by_task(task_id)

        assert len(result) == 3
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_steps_by_task_excludes_completed_when_specified(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """get_steps_by_task can exclude completed steps."""
        task_id = uuid4()

        mock_steps = [
            MagicMock(id=uuid4(), agent_type="worker", status="started"),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_steps
        mock_session.execute.return_value = mock_result

        result = await repository.get_steps_by_task(task_id, include_completed=False)

        assert len(result) == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_steps_by_task_returns_empty_list(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """get_steps_by_task returns empty list when no steps."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_steps_by_task(task_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_steps_by_milestone(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """get_steps_by_milestone returns steps for a milestone."""
        milestone_id = uuid4()

        mock_steps = [
            MagicMock(id=uuid4(), agent_type="worker"),
            MagicMock(id=uuid4(), agent_type="qa"),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_steps
        mock_session.execute.return_value = mock_result

        result = await repository.get_steps_by_milestone(milestone_id)

        assert len(result) == 2
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_steps_by_milestone_returns_empty(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """get_steps_by_milestone returns empty list when no steps."""
        milestone_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_steps_by_milestone(milestone_id)

        assert result == []


class TestAgentStepRepositoryCostBreakdown:
    """Tests for cost breakdown functionality."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> AgentStepRepository:
        """Create repository with mock session."""
        return AgentStepRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_cost_breakdown_by_agent_aggregates_correctly(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """get_cost_breakdown_by_agent aggregates costs by agent type."""
        task_id = uuid4()

        # Create mock steps with different agent types
        mock_steps = [
            MagicMock(
                agent_type="architect",
                cost_usd=Decimal("0.001"),
                input_tokens=50,
                output_tokens=25,
                duration_ms=100,
            ),
            MagicMock(
                agent_type="worker",
                cost_usd=Decimal("0.01"),
                input_tokens=500,
                output_tokens=250,
                duration_ms=2000,
            ),
            MagicMock(
                agent_type="worker",
                cost_usd=Decimal("0.015"),
                input_tokens=750,
                output_tokens=400,
                duration_ms=3000,
            ),
            MagicMock(
                agent_type="qa",
                cost_usd=Decimal("0.005"),
                input_tokens=200,
                output_tokens=100,
                duration_ms=500,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_steps
        mock_session.execute.return_value = mock_result

        result = await repository.get_cost_breakdown_by_agent(task_id)

        assert "architect" in result
        assert "worker" in result
        assert "qa" in result

        # Check architect aggregation
        assert result["architect"]["total_cost_usd"] == Decimal("0.001")
        assert result["architect"]["total_input_tokens"] == 50
        assert result["architect"]["total_output_tokens"] == 25
        assert result["architect"]["step_count"] == 1

        # Check worker aggregation (2 steps)
        assert result["worker"]["total_cost_usd"] == Decimal("0.025")
        assert result["worker"]["total_input_tokens"] == 1250
        assert result["worker"]["total_output_tokens"] == 650
        assert result["worker"]["step_count"] == 2
        assert result["worker"]["total_duration_ms"] == 5000

        # Check qa aggregation
        assert result["qa"]["total_cost_usd"] == Decimal("0.005")
        assert result["qa"]["step_count"] == 1

    @pytest.mark.asyncio
    async def test_get_cost_breakdown_by_agent_handles_null_duration(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """get_cost_breakdown_by_agent handles None duration_ms."""
        task_id = uuid4()

        mock_steps = [
            MagicMock(
                agent_type="worker",
                cost_usd=Decimal("0.01"),
                input_tokens=100,
                output_tokens=50,
                duration_ms=None,  # No duration
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_steps
        mock_session.execute.return_value = mock_result

        result = await repository.get_cost_breakdown_by_agent(task_id)

        assert result["worker"]["total_duration_ms"] == 0

    @pytest.mark.asyncio
    async def test_get_cost_breakdown_by_agent_returns_empty_dict(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """get_cost_breakdown_by_agent returns empty dict when no steps."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_cost_breakdown_by_agent(task_id)

        assert result == {}
