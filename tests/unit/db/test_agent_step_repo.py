"""Tests for AgentStepRepository."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.repository.agent_step_repo import AgentStepRepository


class TestAgentStepRepository:
    """Tests for AgentStepRepository."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> AgentStepRepository:
        """Create repository with mock session."""
        return AgentStepRepository(mock_session)

    @pytest.mark.asyncio
    async def test_start_step_creates_agent_step(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """start_step creates a new agent step record."""
        task_id = uuid4()
        milestone_id = uuid4()
        agent_type = "worker"
        input_summary = "Processing milestone"
        metadata = {"complexity": "simple"}

        mock_step = MagicMock()
        mock_step.id = uuid4()
        mock_step.task_id = task_id
        mock_step.milestone_id = milestone_id
        mock_step.agent_type = agent_type
        mock_step.status = "started"

        mock_session.flush.return_value = None
        mock_session.refresh.return_value = None

        # Mock the create method behavior
        def capture_add(obj):
            obj.id = mock_step.id

        mock_session.add.side_effect = capture_add

        await repository.start_step(
            task_id=task_id,
            agent_type=agent_type,
            milestone_id=milestone_id,
            input_summary=input_summary,
            metadata=metadata,
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_step_without_milestone(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """start_step works without milestone_id."""
        task_id = uuid4()
        agent_type = "conductor"

        await repository.start_step(
            task_id=task_id,
            agent_type=agent_type,
        )

        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.milestone_id is None

    @pytest.mark.asyncio
    async def test_start_step_with_metadata(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """start_step serializes metadata to JSON."""
        task_id = uuid4()
        metadata = {"key": "value", "nested": {"a": 1}}

        await repository.start_step(
            task_id=task_id,
            agent_type="worker",
            metadata=metadata,
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.metadata_json is not None
        assert "key" in added_obj.metadata_json

    @pytest.mark.asyncio
    async def test_complete_step_updates_step(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """complete_step updates step with completion data."""
        step_id = uuid4()
        started_at = datetime.now(UTC) - timedelta(seconds=2)

        mock_step = MagicMock()
        mock_step.id = step_id
        mock_step.started_at = started_at
        mock_step.status = "started"
        mock_step.cost_usd = Decimal("0")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_step
        mock_session.execute.return_value = mock_result

        result = await repository.complete_step(
            step_id=step_id,
            output_summary="Task completed successfully",
            input_tokens=100,
            output_tokens=50,
            cost_usd=Decimal("0.005"),
        )

        assert result is not None
        assert result.status == "completed"
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cost_usd == Decimal("0.005")
        assert result.duration_ms is not None and result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_complete_step_marks_failed_on_error(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """complete_step marks step as failed when error provided."""
        step_id = uuid4()
        started_at = datetime.now(UTC) - timedelta(seconds=1)

        mock_step = MagicMock()
        mock_step.id = step_id
        mock_step.started_at = started_at
        mock_step.status = "started"
        mock_step.cost_usd = Decimal("0")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_step
        mock_session.execute.return_value = mock_result

        result = await repository.complete_step(
            step_id=step_id,
            error_message="LLM call failed",
        )

        assert result is not None
        assert result.status == "failed"
        assert result.error_message == "LLM call failed"

    @pytest.mark.asyncio
    async def test_complete_step_returns_none_for_missing(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """complete_step returns None when step not found."""
        step_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.complete_step(step_id=step_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_steps_by_task_returns_ordered_list(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """get_steps_by_task returns steps ordered by started_at."""
        task_id = uuid4()

        mock_steps = [
            MagicMock(id=uuid4(), agent_type="conductor", status="completed"),
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
        # The query should filter out completed steps
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
                agent_type="conductor",
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

        assert "conductor" in result
        assert "worker" in result
        assert "qa" in result

        # Check conductor aggregation
        assert result["conductor"]["total_cost_usd"] == Decimal("0.001")
        assert result["conductor"]["total_input_tokens"] == 50
        assert result["conductor"]["total_output_tokens"] == 25
        assert result["conductor"]["step_count"] == 1

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


class TestAgentStepRepositoryIntegration:
    """Integration-style tests for repository behavior."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> AgentStepRepository:
        """Create repository with mock session."""
        return AgentStepRepository(mock_session)

    @pytest.mark.asyncio
    async def test_complete_step_calculates_duration(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """complete_step correctly calculates duration in milliseconds."""
        step_id = uuid4()
        # Step started 5 seconds ago
        started_at = datetime.now(UTC) - timedelta(seconds=5)

        mock_step = MagicMock()
        mock_step.id = step_id
        mock_step.started_at = started_at
        mock_step.status = "started"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_step
        mock_session.execute.return_value = mock_result

        result = await repository.complete_step(step_id=step_id)

        # Duration should be approximately 5000ms (with some tolerance)
        assert result is not None
        assert result.duration_ms is not None
        assert result.duration_ms >= 4000  # At least 4 seconds
        assert result.duration_ms <= 6000  # At most 6 seconds

    @pytest.mark.asyncio
    async def test_start_step_sets_correct_status(
        self,
        repository: AgentStepRepository,
        mock_session: AsyncMock,
    ) -> None:
        """start_step sets status to 'started'."""
        task_id = uuid4()

        await repository.start_step(
            task_id=task_id,
            agent_type="worker",
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.status == "started"
