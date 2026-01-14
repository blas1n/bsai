"""Tests for advance node."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.core.qa_agent import QADecision
from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.graph.nodes.advance import advance_node
from agent.graph.state import AgentState, MilestoneData


class TestAdvanceNode:
    """Tests for advance_node."""

    @pytest.mark.asyncio
    async def test_retry_decision(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test advance with retry decision."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model=None,
            generated_prompt=None,
            worker_output=None,
            qa_feedback=None,
            retry_count=0,
        )

        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            user_id="test-user",
            original_request="Test",
            milestones=[milestone],
            current_milestone_index=0,
            current_qa_decision=QADecision.RETRY.value,
            retry_count=0,
        )

        result = await advance_node(state, mock_config, mock_session)

        assert result["retry_count"] == 1
        assert result["should_continue"] is False
        assert result.get("current_qa_decision") is None

    @pytest.mark.asyncio
    async def test_fail_decision(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test advance with fail decision."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.FAILED,
            selected_model=None,
            generated_prompt=None,
            worker_output=None,
            qa_feedback=None,
            retry_count=0,
        )

        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            user_id="test-user",
            original_request="Test",
            milestones=[milestone],
            current_milestone_index=0,
            current_qa_decision=QADecision.FAIL.value,
        )

        result = await advance_node(state, mock_config, mock_session)

        assert result["task_status"] == TaskStatus.FAILED
        assert result["workflow_complete"] is True

    @pytest.mark.asyncio
    async def test_pass_to_next_milestone(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test advancing to next milestone on pass."""
        milestones = [
            MilestoneData(
                id=uuid4(),
                description="Task 1",
                complexity=TaskComplexity.SIMPLE,
                acceptance_criteria="Done",
                status=MilestoneStatus.PASSED,
                selected_model=None,
                generated_prompt=None,
                worker_output=None,
                qa_feedback=None,
                retry_count=0,
            ),
            MilestoneData(
                id=uuid4(),
                description="Task 2",
                complexity=TaskComplexity.SIMPLE,
                acceptance_criteria="Done",
                status=MilestoneStatus.PENDING,
                selected_model=None,
                generated_prompt=None,
                worker_output=None,
                qa_feedback=None,
                retry_count=0,
            ),
        ]

        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            user_id="test-user",
            original_request="Test",
            milestones=milestones,
            current_milestone_index=0,
            current_qa_decision=QADecision.PASS.value,
        )

        result = await advance_node(state, mock_config, mock_session)

        assert result["current_milestone_index"] == 1
        assert result["retry_count"] == 0
        assert result["should_continue"] is True

    @pytest.mark.asyncio
    async def test_pass_completes_workflow(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test workflow completion when last milestone passes."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.PASSED,
            selected_model=None,
            generated_prompt=None,
            worker_output=None,
            qa_feedback=None,
            retry_count=0,
        )

        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            user_id="test-user",
            original_request="Test",
            milestones=[milestone],
            current_milestone_index=0,
            current_qa_decision=QADecision.PASS.value,
        )

        result = await advance_node(state, mock_config, mock_session)

        assert result["task_status"] == TaskStatus.COMPLETED
        assert result["workflow_complete"] is True
