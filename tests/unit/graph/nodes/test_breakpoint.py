"""Tests for breakpoint node."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.graph.nodes.breakpoint import qa_breakpoint_node
from agent.graph.state import AgentState

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_ws_manager() -> MagicMock:
    """Create mock WebSocket manager."""
    manager = MagicMock()
    manager.is_breakpoint_enabled = MagicMock(return_value=True)
    manager.is_paused_at = MagicMock(return_value=False)
    manager.set_paused_at = MagicMock()
    manager.broadcast_to_session = AsyncMock()
    return manager


@pytest.fixture
def mock_config(mock_ws_manager: MagicMock) -> RunnableConfig:
    """Create mock RunnableConfig."""
    return RunnableConfig(
        configurable={
            "ws_manager": mock_ws_manager,
        }
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def base_state() -> AgentState:
    """Create base agent state for testing."""
    session_id = uuid4()
    task_id = uuid4()
    milestone_id = uuid4()

    return {
        "session_id": session_id,
        "task_id": task_id,
        "user_id": "test-user",
        "original_request": "Test request",
        "task_status": TaskStatus.IN_PROGRESS,
        "milestones": [
            {
                "id": milestone_id,
                "description": "Test milestone",
                "complexity": TaskComplexity.MODERATE,
                "acceptance_criteria": "Test criteria",
                "status": MilestoneStatus.IN_PROGRESS,
                "selected_model": "gpt-4",
                "generated_prompt": "Test prompt",
                "worker_output": "Test output",
                "qa_feedback": None,
                "retry_count": 0,
            }
        ],
        "current_milestone_index": 0,
        "breakpoint_enabled": True,
        "breakpoint_nodes": ["qa_breakpoint"],
        "retry_count": 0,
        "context_messages": [],
        "context_summary": None,
        "current_context_tokens": 0,
        "max_context_tokens": 100000,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": "0",
        "needs_compression": False,
        "workflow_complete": False,
        "should_continue": True,
    }


class TestQaBreakpointNode:
    """Tests for qa_breakpoint_node function."""

    @pytest.mark.asyncio
    async def test_skips_breakpoint_when_disabled(
        self,
        mock_ws_manager: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Skips breakpoint when breakpoints are disabled."""
        mock_ws_manager.is_breakpoint_enabled.return_value = False
        base_state["breakpoint_enabled"] = False

        result = await qa_breakpoint_node(base_state, mock_config, mock_session)

        assert result == {}
        mock_ws_manager.set_paused_at.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_already_paused_at_milestone(
        self,
        mock_ws_manager: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Skips breakpoint when already paused at this milestone."""
        mock_ws_manager.is_paused_at.return_value = True

        result = await qa_breakpoint_node(base_state, mock_config, mock_session)

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_cancelled_when_task_cancelled(
        self,
        mock_ws_manager: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Returns cancelled state when task is cancelled."""
        with patch(
            "agent.graph.nodes.breakpoint.check_task_cancelled",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.return_value = True

            result = await qa_breakpoint_node(base_state, mock_config, mock_session)

            assert result["error"] == "Task cancelled by user"
            assert result["task_status"] == TaskStatus.FAILED
            assert result["workflow_complete"] is True

    @pytest.mark.asyncio
    async def test_broadcasts_breakpoint_hit_and_interrupts(
        self,
        mock_ws_manager: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Broadcasts breakpoint hit and interrupts workflow."""
        with (
            patch(
                "agent.graph.nodes.breakpoint.check_task_cancelled",
                new_callable=AsyncMock,
            ) as mock_check,
            patch(
                "agent.graph.nodes.breakpoint.broadcast_breakpoint_hit",
                new_callable=AsyncMock,
            ) as mock_broadcast,
            patch("agent.graph.nodes.breakpoint.interrupt") as mock_interrupt,
        ):
            mock_check.return_value = False
            mock_interrupt.return_value = None  # User resumes without input

            result = await qa_breakpoint_node(base_state, mock_config, mock_session)

            mock_broadcast.assert_called_once()
            mock_ws_manager.set_paused_at.assert_called_once_with(base_state["task_id"], 0)
            mock_interrupt.assert_called_once()
            assert result == {}

    @pytest.mark.asyncio
    async def test_handles_user_modified_input(
        self,
        mock_ws_manager: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Handles user-modified input at breakpoint."""
        with (
            patch(
                "agent.graph.nodes.breakpoint.check_task_cancelled",
                new_callable=AsyncMock,
            ) as mock_check,
            patch(
                "agent.graph.nodes.breakpoint.broadcast_breakpoint_hit",
                new_callable=AsyncMock,
            ),
            patch("agent.graph.nodes.breakpoint.interrupt") as mock_interrupt,
        ):
            mock_check.return_value = False
            mock_interrupt.return_value = {
                "user_input": "Modified output",
                "rejected": False,
            }

            result = await qa_breakpoint_node(base_state, mock_config, mock_session)

            assert "milestones" in result
            assert result["milestones"][0]["worker_output"] == "Modified output"
            assert result["breakpoint_user_input"] == "Modified output"

    @pytest.mark.asyncio
    async def test_handles_rejected_with_feedback(
        self,
        mock_ws_manager: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Handles rejection with feedback - triggers retry."""
        with (
            patch(
                "agent.graph.nodes.breakpoint.check_task_cancelled",
                new_callable=AsyncMock,
            ) as mock_check,
            patch(
                "agent.graph.nodes.breakpoint.broadcast_breakpoint_hit",
                new_callable=AsyncMock,
            ),
            patch("agent.graph.nodes.breakpoint.interrupt") as mock_interrupt,
        ):
            mock_check.return_value = False
            mock_interrupt.return_value = {
                "user_input": "Please fix this issue",
                "rejected": True,
            }

            result = await qa_breakpoint_node(base_state, mock_config, mock_session)

            assert result["qa_decision"] == "fail"
            assert result["milestones"][0]["qa_feedback"] == "Please fix this issue"
            assert result["milestones"][0]["status"] == "fail"

    @pytest.mark.asyncio
    async def test_handles_rejected_without_feedback_cancels_task(
        self,
        mock_ws_manager: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Handles rejection without feedback - cancels task."""
        with (
            patch(
                "agent.graph.nodes.breakpoint.check_task_cancelled",
                new_callable=AsyncMock,
            ) as mock_check,
            patch(
                "agent.graph.nodes.breakpoint.broadcast_breakpoint_hit",
                new_callable=AsyncMock,
            ),
            patch("agent.graph.nodes.breakpoint.interrupt") as mock_interrupt,
        ):
            mock_check.return_value = False
            mock_interrupt.return_value = {
                "user_input": None,
                "rejected": True,
            }

            result = await qa_breakpoint_node(base_state, mock_config, mock_session)

            assert result["error"] == "Task cancelled by user"
            assert result["task_status"] == TaskStatus.FAILED
            assert result["workflow_complete"] is True
            assert result["user_cancelled"] is True

    @pytest.mark.asyncio
    async def test_uses_dynamic_config_over_state(
        self,
        mock_ws_manager: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Uses dynamic config from WebSocket over initial state."""
        # State says disabled, but dynamic config says enabled
        base_state["breakpoint_enabled"] = False
        mock_ws_manager.is_breakpoint_enabled.return_value = True

        with (
            patch(
                "agent.graph.nodes.breakpoint.check_task_cancelled",
                new_callable=AsyncMock,
            ) as mock_check,
            patch(
                "agent.graph.nodes.breakpoint.broadcast_breakpoint_hit",
                new_callable=AsyncMock,
            ),
            patch("agent.graph.nodes.breakpoint.interrupt") as mock_interrupt,
        ):
            mock_check.return_value = False
            mock_interrupt.return_value = None

            await qa_breakpoint_node(base_state, mock_config, mock_session)

            # Should still pause because dynamic config says enabled
            mock_interrupt.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_empty_milestones(
        self,
        mock_ws_manager: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Handles case with no milestones."""
        base_state["milestones"] = []
        base_state["current_milestone_index"] = 0

        with (
            patch(
                "agent.graph.nodes.breakpoint.check_task_cancelled",
                new_callable=AsyncMock,
            ) as mock_check,
            patch(
                "agent.graph.nodes.breakpoint.broadcast_breakpoint_hit",
                new_callable=AsyncMock,
            ) as mock_broadcast,
            patch("agent.graph.nodes.breakpoint.interrupt") as mock_interrupt,
        ):
            mock_check.return_value = False
            mock_interrupt.return_value = None

            result = await qa_breakpoint_node(base_state, mock_config, mock_session)

            mock_broadcast.assert_called_once()
            # Should handle empty milestones gracefully
            assert result == {}


class TestNodeHelpers:
    """Tests for helper functions in nodes __init__."""

    def test_get_ws_manager_returns_manager(self) -> None:
        """Returns ws_manager from config."""
        from agent.graph.nodes import get_ws_manager

        mock_manager = MagicMock()
        config = RunnableConfig(configurable={"ws_manager": mock_manager})

        result = get_ws_manager(config)

        assert result is mock_manager

    def test_get_ws_manager_raises_without_manager(self) -> None:
        """Raises RuntimeError when ws_manager not in config."""
        from agent.graph.nodes import get_ws_manager

        config = RunnableConfig(configurable={})

        with pytest.raises(RuntimeError, match="WebSocket manager not found"):
            get_ws_manager(config)

    def test_get_container_returns_container(self) -> None:
        """Returns container from config."""
        from agent.graph.nodes import get_container

        mock_container = MagicMock()
        config = RunnableConfig(configurable={"container": mock_container})

        result = get_container(config)

        assert result is mock_container

    def test_get_container_raises_without_container(self) -> None:
        """Raises RuntimeError when container not in config."""
        from agent.graph.nodes import get_container

        config = RunnableConfig(configurable={})

        with pytest.raises(RuntimeError, match="Container not found"):
            get_container(config)

    def test_get_mcp_executor_returns_executor(self) -> None:
        """Returns MCP executor from config."""
        from agent.graph.nodes import get_mcp_executor

        mock_executor = MagicMock()
        config = RunnableConfig(configurable={"mcp_executor": mock_executor})

        result = get_mcp_executor(config)

        assert result is mock_executor

    def test_get_mcp_executor_returns_none_when_missing(self) -> None:
        """Returns None when MCP executor not in config."""
        from agent.graph.nodes import get_mcp_executor

        config = RunnableConfig(configurable={})

        result = get_mcp_executor(config)

        assert result is None

    @pytest.mark.asyncio
    async def test_check_task_cancelled_returns_true_for_missing_task(self) -> None:
        """Returns True when task not found."""
        from agent.graph.nodes import check_task_cancelled

        mock_session = AsyncMock()
        task_id = uuid4()

        with patch("agent.graph.nodes.TaskRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            result = await check_task_cancelled(mock_session, task_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_check_task_cancelled_returns_true_for_failed_task(self) -> None:
        """Returns True when task is failed."""
        from agent.graph.nodes import check_task_cancelled

        mock_session = AsyncMock()
        task_id = uuid4()
        mock_task = MagicMock()
        mock_task.status = TaskStatus.FAILED.value

        with patch("agent.graph.nodes.TaskRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_task)
            mock_repo_class.return_value = mock_repo

            result = await check_task_cancelled(mock_session, task_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_check_task_cancelled_returns_true_for_completed_task(self) -> None:
        """Returns True when task is completed."""
        from agent.graph.nodes import check_task_cancelled

        mock_session = AsyncMock()
        task_id = uuid4()
        mock_task = MagicMock()
        mock_task.status = TaskStatus.COMPLETED.value

        with patch("agent.graph.nodes.TaskRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_task)
            mock_repo_class.return_value = mock_repo

            result = await check_task_cancelled(mock_session, task_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_check_task_cancelled_returns_false_for_in_progress(self) -> None:
        """Returns False when task is in progress."""
        from agent.graph.nodes import check_task_cancelled

        mock_session = AsyncMock()
        task_id = uuid4()
        mock_task = MagicMock()
        mock_task.status = TaskStatus.IN_PROGRESS.value

        with patch("agent.graph.nodes.TaskRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_task)
            mock_repo_class.return_value = mock_repo

            result = await check_task_cancelled(mock_session, task_id)

            assert result is False

    @pytest.mark.asyncio
    async def test_check_task_cancelled_returns_false_for_pending(self) -> None:
        """Returns False when task is pending."""
        from agent.graph.nodes import check_task_cancelled

        mock_session = AsyncMock()
        task_id = uuid4()
        mock_task = MagicMock()
        mock_task.status = TaskStatus.PENDING.value

        with patch("agent.graph.nodes.TaskRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_task)
            mock_repo_class.return_value = mock_repo

            result = await check_task_cancelled(mock_session, task_id)

            assert result is False
