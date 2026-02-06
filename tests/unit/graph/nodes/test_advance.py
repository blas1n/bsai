"""Tests for advance node with project_plan flow."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.core.qa_agent import QADecision
from agent.db.models.enums import TaskStatus
from agent.graph.nodes.advance import advance_node
from agent.graph.state import AgentState


def _create_state_with_plan(
    qa_decision: str | None = None,
    retry_count: int = 0,
    error: str | None = None,
    workflow_complete: bool = False,
    tasks: list[dict] | None = None,
    current_task_id: str = "T1",
) -> AgentState:
    """Create state with project plan."""
    if tasks is None:
        tasks = [
            {
                "id": "T1",
                "description": "Task 1",
                "complexity": "SIMPLE",
                "acceptance_criteria": "Done",
                "status": "in_progress",
            }
        ]

    mock_plan = MagicMock()
    mock_plan.plan_data = {"tasks": tasks}
    mock_plan.total_tasks = len(tasks)
    mock_plan.completed_tasks = sum(1 for t in tasks if t.get("status") == "completed")

    state = AgentState(
        session_id=uuid4(),
        task_id=uuid4(),
        user_id="test-user",
        original_request="Test request",
        project_plan=mock_plan,
        current_task_id=current_task_id,
        retry_count=retry_count,
        workflow_complete=workflow_complete,
    )

    if qa_decision:
        state["current_qa_decision"] = qa_decision
    if error:
        state["error"] = error

    return state


class TestAdvanceNode:
    """Tests for advance_node with project_plan."""

    @pytest.mark.asyncio
    async def test_retry_decision(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test advance with retry decision increments retry count."""
        state = _create_state_with_plan(
            qa_decision=QADecision.RETRY.value,
            retry_count=0,
        )

        result = await advance_node(state, mock_config, mock_session)

        assert result["retry_count"] == 1
        assert result["should_continue"] is False
        assert result.get("current_qa_decision") is None

    @pytest.mark.asyncio
    async def test_retry_max_exceeded_fails(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test that exceeding max retries triggers failure."""
        state = _create_state_with_plan(
            qa_decision=QADecision.RETRY.value,
            retry_count=2,  # Will become 3 which equals max
        )

        with patch("agent.graph.nodes.advance.get_agent_settings") as mock_settings:
            mock_settings.return_value = MagicMock(max_milestone_retries=3)
            result = await advance_node(state, mock_config, mock_session)

        assert result["task_status"] == TaskStatus.FAILED
        assert result["workflow_complete"] is True
        assert result["should_continue"] is False

    @pytest.mark.asyncio
    async def test_fail_decision(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test advance with fail decision completes workflow."""
        state = _create_state_with_plan(
            qa_decision=QADecision.FAIL.value,
        )

        result = await advance_node(state, mock_config, mock_session)

        assert result["task_status"] == TaskStatus.FAILED
        assert result["workflow_complete"] is True
        assert result["should_continue"] is False

    @pytest.mark.asyncio
    async def test_pass_advances_to_next_task(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test advancing to next task on pass with multiple tasks."""
        tasks = [
            {
                "id": "T1",
                "description": "Task 1",
                "complexity": "SIMPLE",
                "acceptance_criteria": "Done",
                "status": "in_progress",
            },
            {
                "id": "T2",
                "description": "Task 2",
                "complexity": "SIMPLE",
                "acceptance_criteria": "Done",
                "status": "pending",
                "depends_on": ["T1"],
            },
        ]
        state = _create_state_with_plan(
            qa_decision=QADecision.PASS.value,
            tasks=tasks,
            current_task_id="T1",
        )

        with patch("agent.graph.nodes.advance.ProjectPlanRepository") as MockRepo:
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo

            result = await advance_node(state, mock_config, mock_session)

        assert result["current_task_id"] == "T2"
        assert result["retry_count"] == 0
        assert result["should_continue"] is True

    @pytest.mark.asyncio
    async def test_pass_completes_workflow_on_last_task(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test workflow completion when last task passes."""
        tasks = [
            {
                "id": "T1",
                "description": "Only task",
                "complexity": "SIMPLE",
                "acceptance_criteria": "Done",
                "status": "in_progress",
            },
        ]
        state = _create_state_with_plan(
            qa_decision=QADecision.PASS.value,
            tasks=tasks,
            current_task_id="T1",
        )

        with patch("agent.graph.nodes.advance.ProjectPlanRepository") as MockRepo:
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo

            result = await advance_node(state, mock_config, mock_session)

        assert result["task_status"] == TaskStatus.COMPLETED
        assert result["workflow_complete"] is True
        assert result["should_continue"] is False

    @pytest.mark.asyncio
    async def test_no_project_plan_returns_error(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test error handling when no project plan exists."""
        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            user_id="test-user",
            original_request="Test",
            project_plan=None,
            current_qa_decision=QADecision.PASS.value,
        )

        result = await advance_node(state, mock_config, mock_session)

        assert result["error"] == "No project plan available"
        assert result["error_node"] == "advance"
        assert result["workflow_complete"] is True

    @pytest.mark.asyncio
    async def test_early_termination_on_error(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test early termination when error already exists."""
        state = _create_state_with_plan(
            error="Previous error",
        )

        result = await advance_node(state, mock_config, mock_session)

        assert result["task_status"] == TaskStatus.FAILED
        assert result["workflow_complete"] is True
        assert result["should_continue"] is False

    @pytest.mark.asyncio
    async def test_early_termination_when_workflow_complete(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test early termination when workflow already complete."""
        state = _create_state_with_plan(
            workflow_complete=True,
        )

        result = await advance_node(state, mock_config, mock_session)

        assert result["task_status"] == TaskStatus.FAILED
        assert result["workflow_complete"] is True
