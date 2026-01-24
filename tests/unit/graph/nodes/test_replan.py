"""Tests for replan node."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.edges import MAX_REPLAN_ITERATIONS
from agent.graph.nodes.replan import (
    _apply_modifications,
    replan_node,
)
from agent.graph.state import AgentState, MilestoneData
from agent.llm.schemas import ConductorReplanOutput, MilestoneModification, MilestoneSchema


def _make_milestone(
    description: str = "Test milestone",
    complexity: TaskComplexity = TaskComplexity.SIMPLE,
    status: MilestoneStatus = MilestoneStatus.PENDING,
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
        worker_output=None,
        qa_feedback=None,
        retry_count=0,
    )


def _make_state(
    milestones: list[MilestoneData] | None = None,
    current_index: int = 0,
    replan_count: int = 0,
    needs_replan: bool = True,
    replan_reason: str = "Test reason",
) -> AgentState:
    """Helper to create test state."""
    return AgentState(
        session_id=uuid4(),
        task_id=uuid4(),
        user_id="test-user",
        original_request="Test request",
        milestones=milestones or [_make_milestone()],
        current_milestone_index=current_index,
        replan_count=replan_count,
        needs_replan=needs_replan,
        replan_reason=replan_reason,
        current_observations=["Observation 1"],
        current_qa_feedback="QA feedback",
    )


class TestReplanNode:
    """Tests for replan_node function."""

    @pytest.mark.asyncio
    async def test_max_replan_exceeded(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test that max replan limit is enforced."""
        state = _make_state(replan_count=MAX_REPLAN_ITERATIONS)

        result = await replan_node(state, mock_config, mock_session)

        assert result["error"] == "Maximum replan iterations exceeded"
        assert result["error_node"] == "replan"
        assert result["workflow_complete"] is True

    @pytest.mark.asyncio
    async def test_successful_replan(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Test successful replanning flow."""
        milestones = [
            _make_milestone("Milestone 1", status=MilestoneStatus.PASSED),
            _make_milestone("Milestone 2", status=MilestoneStatus.IN_PROGRESS),
        ]
        state = _make_state(milestones=milestones, current_index=1)

        # Mock conductor replan output
        mock_replan_output = ConductorReplanOutput(
            analysis="Analysis of the situation",
            modifications=[
                MilestoneModification(
                    action="ADD",
                    reason="Need additional step",
                    new_milestone=MilestoneSchema(
                        description="New milestone",
                        complexity="SIMPLE",
                        acceptance_criteria="New criteria",
                    ),
                )
            ],
            confidence=0.85,
            reasoning="Reasoning for changes",
        )

        with (
            patch("agent.graph.nodes.replan.ConductorAgent") as MockConductor,
            patch("agent.graph.nodes.replan.MilestoneRepository") as MockRepo,
        ):
            mock_conductor = AsyncMock()
            mock_conductor.replan_based_on_execution.return_value = mock_replan_output
            MockConductor.return_value = mock_conductor

            mock_repo = AsyncMock()
            mock_repo.get_by_task_id.return_value = []
            mock_repo.get_by_id.return_value = None
            mock_repo.create.return_value = MagicMock()
            MockRepo.return_value = mock_repo

            result = await replan_node(state, mock_config, mock_session)

        # Verify successful result
        assert "error" not in result
        assert result["replan_count"] == 1
        assert result["needs_replan"] is False
        assert result["replan_reason"] is None
        assert result["retry_count"] == 0
        assert result["plan_confidence"] == 0.85
        assert len(result["plan_modifications"]) == 1
        assert len(result["milestones"]) == 3  # 2 original + 1 added

        # Verify event was emitted
        mock_event_bus.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_replan_exception_handling(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test exception handling in replan node."""
        state = _make_state()

        with patch("agent.graph.nodes.replan.ConductorAgent") as MockConductor:
            mock_conductor = AsyncMock()
            mock_conductor.replan_based_on_execution.side_effect = Exception("Conductor error")
            MockConductor.return_value = mock_conductor

            result = await replan_node(state, mock_config, mock_session)

        assert result["error"] == "Conductor error"
        assert result["error_node"] == "replan"


class TestApplyModifications:
    """Tests for _apply_modifications function."""

    def test_add_modification(self) -> None:
        """Test adding a new milestone."""
        milestones = [_make_milestone("Original")]
        modifications = [
            MilestoneModification(
                action="ADD",
                reason="Need new step",
                new_milestone=MilestoneSchema(
                    description="Added milestone",
                    complexity="MODERATE",
                    acceptance_criteria="Added criteria",
                ),
            )
        ]

        result = _apply_modifications(
            milestones=milestones,
            modifications=modifications,
            current_index=0,
            replan_iteration=1,
        )

        assert len(result) == 2
        assert result[1]["description"] == "Added milestone"
        assert result[1]["complexity"] == TaskComplexity.MODERATE
        assert result[1]["is_modified"] is True
        assert result[1]["added_at_replan"] == 1

    def test_modify_milestone(self) -> None:
        """Test modifying an existing milestone."""
        milestones = [
            _make_milestone("First"),
            _make_milestone("Second"),
        ]
        modifications = [
            MilestoneModification(
                action="MODIFY",
                target_index=1,
                reason="Update description",
                new_milestone=MilestoneSchema(
                    description="Modified second",
                    complexity="COMPLEX",
                    acceptance_criteria="Updated criteria",
                ),
            )
        ]

        result = _apply_modifications(
            milestones=milestones,
            modifications=modifications,
            current_index=0,
            replan_iteration=1,
        )

        assert len(result) == 2
        assert result[1]["description"] == "Modified second"
        assert result[1]["complexity"] == TaskComplexity.COMPLEX
        assert result[1]["is_modified"] is True

    def test_remove_milestone(self) -> None:
        """Test removing a milestone."""
        milestones = [
            _make_milestone("First"),
            _make_milestone("Second"),
            _make_milestone("Third"),
        ]
        modifications = [
            MilestoneModification(
                action="REMOVE",
                target_index=2,
                reason="Not needed",
            )
        ]

        result = _apply_modifications(
            milestones=milestones,
            modifications=modifications,
            current_index=0,
            replan_iteration=1,
        )

        assert len(result) == 2
        assert result[0]["description"] == "First"
        assert result[1]["description"] == "Second"

    def test_cannot_modify_past_milestones(self) -> None:
        """Test that milestones before current index cannot be modified."""
        milestones = [
            _make_milestone("First"),
            _make_milestone("Second"),
            _make_milestone("Third"),
        ]
        modifications = [
            MilestoneModification(
                action="MODIFY",
                target_index=0,  # Before current_index=1
                reason="Try to modify past",
                new_milestone=MilestoneSchema(
                    description="Should not change",
                    complexity="TRIVIAL",
                    acceptance_criteria="New criteria",
                ),
            )
        ]

        result = _apply_modifications(
            milestones=milestones,
            modifications=modifications,
            current_index=1,  # First milestone already passed
            replan_iteration=1,
        )

        # First milestone should remain unchanged
        assert result[0]["description"] == "First"

    def test_cannot_remove_past_milestones(self) -> None:
        """Test that milestones before current index cannot be removed."""
        milestones = [
            _make_milestone("First"),
            _make_milestone("Second"),
        ]
        modifications = [
            MilestoneModification(
                action="REMOVE",
                target_index=0,  # Before current_index=1
                reason="Try to remove past",
            )
        ]

        result = _apply_modifications(
            milestones=milestones,
            modifications=modifications,
            current_index=1,
            replan_iteration=1,
        )

        # All milestones should remain
        assert len(result) == 2

    def test_reorder_marks_as_modified(self) -> None:
        """Test that reorder action marks milestone as modified."""
        milestones = [
            _make_milestone("First"),
            _make_milestone("Second"),
        ]
        modifications = [
            MilestoneModification(
                action="REORDER",
                target_index=1,
                reason="Reorder milestone",
            )
        ]

        result = _apply_modifications(
            milestones=milestones,
            modifications=modifications,
            current_index=0,
            replan_iteration=1,
        )

        assert result[1]["is_modified"] is True

    def test_multiple_modifications(self) -> None:
        """Test applying multiple modifications in sequence.

        Note: REMOVE uses target_index adjusted by index_offset from previous
        modifications. So if ADD adds 1 item first, REMOVE with target_index=3
        will delete the item at adjusted index 3+1=4.
        """
        milestones = [
            _make_milestone("First"),
            _make_milestone("Second"),
            _make_milestone("Third"),
        ]
        modifications = [
            # First: REMOVE Third (index 2 > current_index 0)
            MilestoneModification(
                action="REMOVE",
                target_index=2,
                reason="Remove third",
            ),
            # Then: ADD new milestone
            MilestoneModification(
                action="ADD",
                reason="Add new milestone",
                new_milestone=MilestoneSchema(
                    description="Added",
                    complexity="SIMPLE",
                    acceptance_criteria="Added criteria",
                ),
            ),
        ]

        result = _apply_modifications(
            milestones=milestones,
            modifications=modifications,
            current_index=0,
            replan_iteration=1,
        )

        # 3 original - 1 removed + 1 added = 3
        assert len(result) == 3
        descriptions = [m["description"] for m in result]
        assert "Added" in descriptions
        assert "Third" not in descriptions
        assert "First" in descriptions
        assert "Second" in descriptions

    def test_add_with_specific_target_index(self) -> None:
        """Test adding milestone at specific index."""
        milestones = [
            _make_milestone("First"),
            _make_milestone("Second"),
            _make_milestone("Third"),
        ]
        modifications = [
            MilestoneModification(
                action="ADD",
                target_index=1,
                reason="Add at specific position",
                new_milestone=MilestoneSchema(
                    description="Inserted",
                    complexity="SIMPLE",
                    acceptance_criteria="Insert criteria",
                ),
            )
        ]

        result = _apply_modifications(
            milestones=milestones,
            modifications=modifications,
            current_index=0,
            replan_iteration=1,
        )

        # Insert should be at least after current_index
        assert len(result) == 4
        assert result[1]["description"] == "Inserted"

    def test_empty_modifications(self) -> None:
        """Test with no modifications."""
        milestones = [_make_milestone("Only")]
        modifications: list[Any] = []

        result = _apply_modifications(
            milestones=milestones,
            modifications=modifications,
            current_index=0,
            replan_iteration=1,
        )

        assert len(result) == 1
        assert result[0]["description"] == "Only"
