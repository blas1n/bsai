"""Tests for recovery node."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.nodes.recovery import (
    _collect_failure_reasons,
    _create_milestones_from_plan,
    _summarize_failed_approach,
    recovery_node,
)
from agent.graph.state import AgentState, MilestoneData


def _make_milestone(
    description: str = "Test milestone",
    complexity: TaskComplexity = TaskComplexity.SIMPLE,
    status: MilestoneStatus = MilestoneStatus.PENDING,
    qa_feedback: str | None = None,
    worker_output: str | None = None,
) -> MilestoneData:
    """Helper to create test milestone."""
    return MilestoneData(
        id=uuid4(),
        description=description,
        complexity=complexity,
        acceptance_criteria="Test criteria",
        status=status,
        selected_model="gpt-4o-mini",
        generated_prompt=None,
        worker_output=worker_output,
        qa_feedback=qa_feedback,
        retry_count=0,
    )


def _make_state(
    milestones: list[MilestoneData] | None = None,
    strategy_retry_attempted: bool = False,
    error: str | None = None,
    replan_reason: str | None = None,
) -> AgentState:
    """Helper to create test state."""
    return AgentState(
        session_id=uuid4(),
        task_id=uuid4(),
        user_id="test-user",
        original_request="Test request",
        milestones=milestones or [_make_milestone()],
        current_milestone_index=0,
        strategy_retry_attempted=strategy_retry_attempted,
        error=error,
        replan_reason=replan_reason,
    )


class TestSummarizeFailedApproach:
    """Tests for _summarize_failed_approach helper."""

    def test_empty_milestones(self) -> None:
        """Test with no milestones."""
        result = _summarize_failed_approach([])
        assert result == "No approach was attempted"

    def test_single_milestone(self) -> None:
        """Test with single milestone."""
        milestones = [_make_milestone("Do something", status=MilestoneStatus.FAILED)]
        result = _summarize_failed_approach(milestones)
        assert "1. Do something [failed]" in result

    def test_multiple_milestones(self) -> None:
        """Test with multiple milestones."""
        milestones = [
            _make_milestone("First step", status=MilestoneStatus.PASSED),
            _make_milestone("Second step", status=MilestoneStatus.IN_PROGRESS),
            _make_milestone("Third step", status=MilestoneStatus.PENDING),
        ]
        result = _summarize_failed_approach(milestones)
        assert "1. First step [passed]" in result
        assert "2. Second step [in_progress]" in result
        assert "3. Third step [pending]" in result


class TestCollectFailureReasons:
    """Tests for _collect_failure_reasons helper."""

    def test_error_in_state(self) -> None:
        """Test collecting error from state."""
        state = _make_state(error="Something went wrong")
        reasons = _collect_failure_reasons(state)
        assert "Error: Something went wrong" in reasons

    def test_qa_feedback_in_milestones(self) -> None:
        """Test collecting QA feedback from milestones."""
        milestones = [
            _make_milestone(qa_feedback="QA: Output is incorrect"),
        ]
        state = _make_state(milestones=milestones)
        reasons = _collect_failure_reasons(state)
        assert any("QA: Output is incorrect" in r for r in reasons)

    def test_replan_reason(self) -> None:
        """Test collecting replan reason."""
        state = _make_state(replan_reason="BLOCKED: Cannot proceed")
        reasons = _collect_failure_reasons(state)
        assert "Replan reason: BLOCKED: Cannot proceed" in reasons

    def test_no_reasons(self) -> None:
        """Test when no specific reasons exist."""
        state = _make_state()
        reasons = _collect_failure_reasons(state)
        assert "Unknown failure" in reasons[0]


class TestCreateMilestonesFromPlan:
    """Tests for _create_milestones_from_plan helper."""

    def test_create_from_plan_with_strings(self) -> None:
        """Test creating milestones from conductor plan with string complexity."""
        plan: list[dict[str, Any]] = [
            {
                "description": "First milestone",
                "complexity": "SIMPLE",
                "acceptance_criteria": "Must work",
            },
            {
                "description": "Second milestone",
                "complexity": "MODERATE",
                "acceptance_criteria": "Must be correct",
            },
        ]
        milestones = _create_milestones_from_plan(plan)

        assert len(milestones) == 2
        assert milestones[0]["description"] == "First milestone"
        assert milestones[0]["complexity"] == TaskComplexity.SIMPLE
        assert milestones[0]["status"] == MilestoneStatus.PENDING
        assert milestones[1]["description"] == "Second milestone"
        assert milestones[1]["complexity"] == TaskComplexity.MODERATE

    def test_create_from_plan_with_enums(self) -> None:
        """Test creating milestones from conductor plan with TaskComplexity enum."""
        plan: list[dict[str, Any]] = [
            {
                "description": "Milestone with enum",
                "complexity": TaskComplexity.COMPLEX,
                "acceptance_criteria": "Must be correct",
            },
        ]
        milestones = _create_milestones_from_plan(plan)

        assert len(milestones) == 1
        assert milestones[0]["complexity"] == TaskComplexity.COMPLEX


class TestRecoveryNode:
    """Tests for recovery_node function."""

    @pytest.mark.asyncio
    async def test_first_failure_triggers_strategy_retry(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Test that first failure attempts strategy retry."""
        state = _make_state(
            strategy_retry_attempted=False,
            error="Max retries exceeded",
        )

        # Mock conductor rethink_strategy - return strings for complexity
        new_plan: list[dict[str, Any]] = [
            {
                "description": "Alternative approach",
                "complexity": "MODERATE",
                "acceptance_criteria": "Works differently",
            },
        ]

        with patch("agent.graph.nodes.recovery.ConductorAgent") as MockConductor:
            mock_conductor = AsyncMock()
            mock_conductor.rethink_strategy.return_value = new_plan
            MockConductor.return_value = mock_conductor

            result = await recovery_node(state, mock_config, mock_session)

        # Verify strategy retry was attempted
        assert result["strategy_retry_attempted"] is True
        assert result.get("error") is None
        assert result["workflow_complete"] is False
        assert len(result["milestones"]) == 1
        assert result["milestones"][0]["description"] == "Alternative approach"
        assert result["current_milestone_index"] == 0
        assert result["retry_count"] == 0
        assert result["replan_count"] == 0

    @pytest.mark.asyncio
    async def test_second_failure_generates_report(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Test that second failure prepares failure report context."""
        milestones = [
            _make_milestone("Step 1", status=MilestoneStatus.PASSED, worker_output="Output 1"),
            _make_milestone("Step 2", status=MilestoneStatus.FAILED, qa_feedback="Failed QA"),
        ]
        state = _make_state(
            strategy_retry_attempted=True,
            milestones=milestones,
            error="Still failing",
        )

        result = await recovery_node(state, mock_config, mock_session)

        # Verify failure report context is prepared
        assert result["strategy_retry_attempted"] is True
        assert result["workflow_complete"] is True
        assert "failure_context" in result

        failure_context = result["failure_context"]
        assert failure_context["original_request"] == "Test request"
        assert len(failure_context["attempted_milestones"]) == 2
        assert failure_context["final_error"] == "Still failing"

        # Verify partial results extracted
        assert len(failure_context["partial_results"]) == 1
        assert failure_context["partial_results"][0]["description"] == "Step 1"

    @pytest.mark.asyncio
    async def test_strategy_retry_failure_falls_to_report(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Test that if strategy retry fails, we fall through to report."""
        state = _make_state(
            strategy_retry_attempted=False,
            error="Original error",
        )

        with patch("agent.graph.nodes.recovery.ConductorAgent") as MockConductor:
            mock_conductor = AsyncMock()
            mock_conductor.rethink_strategy.side_effect = Exception("Conductor failed")
            MockConductor.return_value = mock_conductor

            result = await recovery_node(state, mock_config, mock_session)

        # Should fall through to failure report
        assert result["strategy_retry_attempted"] is True
        assert result["workflow_complete"] is True
        assert "failure_context" in result

    @pytest.mark.asyncio
    async def test_events_emitted_on_strategy_retry(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Test that events are emitted during strategy retry."""
        state = _make_state(strategy_retry_attempted=False)

        with patch("agent.graph.nodes.recovery.ConductorAgent") as MockConductor:
            mock_conductor = AsyncMock()
            mock_conductor.rethink_strategy.return_value = [
                {"description": "New plan", "complexity": "SIMPLE", "acceptance_criteria": "OK"},
            ]
            MockConductor.return_value = mock_conductor

            await recovery_node(state, mock_config, mock_session)

        # Verify events were emitted (at least started and completed)
        assert mock_event_bus.emit.call_count >= 2
