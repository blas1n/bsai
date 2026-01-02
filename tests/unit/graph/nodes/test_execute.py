"""Tests for execute worker node."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.nodes.execute import execute_worker_node
from agent.graph.state import AgentState, MilestoneData
from agent.llm import LLMResponse, UsageInfo


class TestExecuteWorkerNode:
    """Tests for execute_worker_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test successful worker execution."""
        with (
            patch("agent.graph.nodes.execute.WorkerAgent") as MockWorker,
            patch("agent.graph.nodes.execute.broadcast_agent_started", new_callable=AsyncMock),
            patch("agent.graph.nodes.execute.broadcast_agent_completed", new_callable=AsyncMock),
            patch("agent.graph.nodes.execute.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.execute.extract_artifacts", return_value=[]),
        ):
            mock_worker = AsyncMock()
            mock_response = LLMResponse(
                content="Task completed successfully",
                usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
                model="gpt-4o-mini",
            )
            mock_worker.execute_milestone.return_value = mock_response
            MockWorker.return_value = mock_worker

            # Setup mock repos
            mock_milestone_repo = MagicMock()
            mock_milestone_repo.update_llm_usage = AsyncMock()
            mock_milestone_repo.update = AsyncMock()
            MockMilestoneRepo.return_value = mock_milestone_repo

            result = await execute_worker_node(state_with_milestone, mock_config, mock_session)

            assert result["current_output"] == "Task completed successfully"
            assert result["milestones"][0]["worker_output"] == "Task completed successfully"
            assert len(result["context_messages"]) == 2  # user + assistant
            assert result["current_context_tokens"] == 150

    @pytest.mark.asyncio
    async def test_retry_with_feedback(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test worker retry with QA feedback."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output="Previous output",
            qa_feedback=None,
            retry_count=0,
        )

        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
            milestones=[milestone],
            current_milestone_index=0,
            retry_count=1,
            current_qa_feedback="Please fix the error",
            context_messages=[],
            current_context_tokens=0,
        )

        with (
            patch("agent.graph.nodes.execute.WorkerAgent") as MockWorker,
            patch("agent.graph.nodes.execute.broadcast_agent_started", new_callable=AsyncMock),
            patch("agent.graph.nodes.execute.broadcast_agent_completed", new_callable=AsyncMock),
            patch("agent.graph.nodes.execute.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.execute.extract_artifacts", return_value=[]),
        ):
            mock_worker = AsyncMock()
            mock_response = LLMResponse(
                content="Fixed output",
                usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
                model="gpt-4o-mini",
            )
            mock_worker.retry_with_feedback.return_value = mock_response
            MockWorker.return_value = mock_worker

            # Setup mock repos
            mock_milestone_repo = MagicMock()
            mock_milestone_repo.update_llm_usage = AsyncMock()
            mock_milestone_repo.update = AsyncMock()
            MockMilestoneRepo.return_value = mock_milestone_repo

            result = await execute_worker_node(state, mock_config, mock_session)

            mock_worker.retry_with_feedback.assert_called_once()
            assert result["current_output"] == "Fixed output"
