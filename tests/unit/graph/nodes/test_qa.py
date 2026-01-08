"""Tests for QA verification node."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.nodes.qa import verify_qa_node
from agent.graph.state import AgentState, MilestoneData


class TestVerifyQaNode:
    """Tests for verify_qa_node."""

    @pytest.mark.asyncio
    async def test_pass_decision(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA pass decision."""
        from agent.core import QADecision

        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output="Good output",
            qa_feedback=None,
            retry_count=0,
        )

        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            user_id="test-user-123",
            original_request="Test",
            milestones=[milestone],
            current_milestone_index=0,
            retry_count=0,
        )

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch("agent.graph.nodes.qa.broadcast_agent_started", new_callable=AsyncMock),
            patch("agent.graph.nodes.qa.broadcast_agent_completed", new_callable=AsyncMock),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (QADecision.PASS, "Looks good")
            MockQA.return_value = mock_qa

            result = await verify_qa_node(state, mock_config, mock_session)

            assert result["current_qa_decision"] == "pass"
            assert result["milestones"][0]["status"] == MilestoneStatus.PASSED
