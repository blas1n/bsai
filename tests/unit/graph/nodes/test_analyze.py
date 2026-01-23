"""Tests for analyze node."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import TaskComplexity, TaskStatus
from agent.graph.nodes.analyze import analyze_task_node
from agent.graph.state import AgentState


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
