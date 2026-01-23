"""Tests for analyze node."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import TaskComplexity, TaskStatus
from agent.graph.nodes.analyze import analyze_task_node
from agent.graph.state import AgentState
from agent.llm.schemas import ChatMessage


class TestAnalyzeTaskNode:
    """Tests for analyze_task_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test successful task analysis."""
        with (
            patch("agent.graph.nodes.analyze.ConductorAgent") as MockConductor,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Mock memory context retrieval
            mock_get_memory_context.return_value = ([], "")

            mock_conductor = AsyncMock()
            mock_conductor.analyze_and_plan.return_value = [
                {
                    "description": "Setup project",
                    "complexity": TaskComplexity.SIMPLE,
                    "acceptance_criteria": "Project initialized",
                }
            ]
            MockConductor.return_value = mock_conductor

            mock_repo = AsyncMock()
            mock_milestone = MagicMock()
            mock_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = [mock_milestone]
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(base_state, mock_config, mock_session)

            assert len(result["milestones"]) == 1
            assert result["current_milestone_index"] == 0
            assert result["task_status"] == TaskStatus.IN_PROGRESS
            assert result["retry_count"] == 0

    @pytest.mark.asyncio
    async def test_error_handling(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test error handling in analyze_task."""
        with (
            patch("agent.graph.nodes.analyze.ConductorAgent") as MockConductor,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Mock memory context retrieval
            mock_get_memory_context.return_value = ([], "")

            mock_conductor = AsyncMock()
            mock_conductor.analyze_and_plan.side_effect = ValueError("LLM error")
            MockConductor.return_value = mock_conductor

            result = await analyze_task_node(base_state, mock_config, mock_session)

            assert result["error"] == "LLM error"
            assert result["error_node"] == "analyze_task"
            assert result["task_status"] == TaskStatus.FAILED
            assert result["workflow_complete"] is True

    @pytest.mark.asyncio
    async def test_with_handover_context(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test task analysis with handover context from previous task (covers lines 73-75)."""
        # Add context message with handover context
        handover_msg = ChatMessage(
            role="system",
            content="Context from previous task: User completed setup successfully.",
        )
        state_with_handover = AgentState(**{**base_state, "context_messages": [handover_msg]})

        with (
            patch("agent.graph.nodes.analyze.ConductorAgent") as MockConductor,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Mock memory context retrieval with actual context
            mock_get_memory_context.return_value = ([], "Related memory: previous project info")

            mock_conductor = AsyncMock()
            mock_conductor.analyze_and_plan.return_value = [
                {
                    "description": "Continue from previous",
                    "complexity": TaskComplexity.MODERATE,
                    "acceptance_criteria": "Task completed",
                }
            ]
            MockConductor.return_value = mock_conductor

            mock_repo = AsyncMock()
            mock_milestone = MagicMock()
            mock_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = [mock_milestone]
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(state_with_handover, mock_config, mock_session)

            # Verify conductor was called with combined context
            mock_conductor.analyze_and_plan.assert_called_once()
            call_kwargs = mock_conductor.analyze_and_plan.call_args[1]
            assert "Context from previous task" in call_kwargs["memory_context"]
            assert "Related memory" in call_kwargs["memory_context"]

            assert len(result["milestones"]) == 1
            assert result["task_status"] == TaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_with_only_handover_context(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test task analysis with only handover context (covers lines 80-85)."""
        handover_msg = ChatMessage(
            role="system",
            content="Context from previous task: User completed phase 1.",
        )
        state_with_handover = AgentState(**{**base_state, "context_messages": [handover_msg]})

        with (
            patch("agent.graph.nodes.analyze.ConductorAgent") as MockConductor,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # No memory context, only handover
            mock_get_memory_context.return_value = ([], None)

            mock_conductor = AsyncMock()
            mock_conductor.analyze_and_plan.return_value = [
                {
                    "description": "Phase 2",
                    "complexity": "simple",  # String complexity (lowercase) to test conversion
                    "acceptance_criteria": "Phase 2 done",
                }
            ]
            MockConductor.return_value = mock_conductor

            mock_repo = AsyncMock()
            mock_milestone = MagicMock()
            mock_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = [mock_milestone]
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(state_with_handover, mock_config, mock_session)

            # Verify conductor was called with handover context only
            call_kwargs = mock_conductor.analyze_and_plan.call_args[1]
            assert "Context from previous task" in call_kwargs["memory_context"]

            assert len(result["milestones"]) == 1

    @pytest.mark.asyncio
    async def test_complexity_string_conversion(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test complexity string is converted to TaskComplexity enum (covers line 130)."""
        with (
            patch("agent.graph.nodes.analyze.ConductorAgent") as MockConductor,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            mock_get_memory_context.return_value = ([], "")

            mock_conductor = AsyncMock()
            # Return complexity as string instead of enum
            mock_conductor.analyze_and_plan.return_value = [
                {
                    "description": "Complex task",
                    "complexity": "complex",  # String (lowercase), not enum
                    "acceptance_criteria": "Task done",
                }
            ]
            MockConductor.return_value = mock_conductor

            mock_repo = AsyncMock()
            mock_milestone = MagicMock()
            mock_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = [mock_milestone]
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(base_state, mock_config, mock_session)

            assert len(result["milestones"]) == 1
            assert result["milestones"][0]["complexity"] == TaskComplexity.COMPLEX

    @pytest.mark.asyncio
    async def test_milestone_missing_db_id_fallback(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test fallback UUID generation when DB milestone is missing (covers lines 118-119)."""
        with (
            patch("agent.graph.nodes.analyze.ConductorAgent") as MockConductor,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            mock_get_memory_context.return_value = ([], "")

            mock_conductor = AsyncMock()
            # Return 2 milestones
            mock_conductor.analyze_and_plan.return_value = [
                {
                    "description": "Task 1",
                    "complexity": TaskComplexity.SIMPLE,
                    "acceptance_criteria": "Done 1",
                },
                {
                    "description": "Task 2",
                    "complexity": TaskComplexity.MODERATE,
                    "acceptance_criteria": "Done 2",
                },
            ]
            MockConductor.return_value = mock_conductor

            mock_repo = AsyncMock()
            # Only return 1 DB milestone (less than returned by conductor)
            mock_milestone = MagicMock()
            mock_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = [mock_milestone]
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(base_state, mock_config, mock_session)

            # Should still create 2 milestones with fallback UUIDs
            assert len(result["milestones"]) == 2
            # First milestone has DB ID
            assert result["milestones"][0]["id"] == mock_milestone.id
            # Second milestone has generated fallback ID
            assert result["milestones"][1]["id"] is not None

    @pytest.mark.asyncio
    async def test_with_existing_milestones(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test task analysis with existing milestones from previous tasks."""
        with (
            patch("agent.graph.nodes.analyze.ConductorAgent") as MockConductor,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            mock_get_memory_context.return_value = ([], "")

            mock_conductor = AsyncMock()
            mock_conductor.analyze_and_plan.return_value = [
                {
                    "description": "New task",
                    "complexity": TaskComplexity.SIMPLE,
                    "acceptance_criteria": "New task done",
                }
            ]
            MockConductor.return_value = mock_conductor

            mock_repo = AsyncMock()
            mock_milestone = MagicMock()
            mock_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = [mock_milestone]
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(state_with_milestone, mock_config, mock_session)

            # Should have 2 milestones: 1 existing + 1 new
            assert len(result["milestones"]) == 2
            # Current index should point to first new milestone
            assert result["current_milestone_index"] == 1

    @pytest.mark.asyncio
    async def test_with_only_memory_context(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test task analysis with only memory context (no handover)."""
        with (
            patch("agent.graph.nodes.analyze.ConductorAgent") as MockConductor,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Only memory context, no handover
            mock_get_memory_context.return_value = (
                [{"content": "memory1"}],
                "Relevant memory context here",
            )

            mock_conductor = AsyncMock()
            mock_conductor.analyze_and_plan.return_value = [
                {
                    "description": "Memory-informed task",
                    "complexity": TaskComplexity.SIMPLE,
                    "acceptance_criteria": "Task done",
                }
            ]
            MockConductor.return_value = mock_conductor

            mock_repo = AsyncMock()
            mock_milestone = MagicMock()
            mock_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = [mock_milestone]
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(base_state, mock_config, mock_session)

            # Verify conductor was called with memory context
            call_kwargs = mock_conductor.analyze_and_plan.call_args[1]
            assert call_kwargs["memory_context"] == "Relevant memory context here"

            assert result["memory_context"] == "Relevant memory context here"
            assert result["relevant_memories"] == [{"content": "memory1"}]
