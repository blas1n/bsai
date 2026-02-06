"""Tests for graph/nodes/__init__.py utilities."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import TaskStatus
from agent.graph.nodes import (
    Node,
    NodeContext,
    check_task_cancelled,
    get_breakpoint_service,
    get_container,
    get_event_bus,
    get_mcp_executor,
    get_ws_manager_optional,
)


class TestNode:
    """Tests for Node enum."""

    def test_node_values(self) -> None:
        """Test Node enum has expected values."""
        assert Node.ANALYZE_TASK == "analyze_task"
        assert Node.SELECT_LLM == "select_llm"
        assert Node.GENERATE_PROMPT == "generate_prompt"
        assert Node.EXECUTE_WORKER == "execute_worker"
        assert Node.VERIFY_QA == "verify_qa"
        assert Node.CHECK_CONTEXT == "check_context"
        assert Node.SUMMARIZE == "summarize"
        assert Node.ADVANCE == "advance"
        assert Node.GENERATE_RESPONSE == "generate_response"

    def test_node_str_enum(self) -> None:
        """Test Node is a string enum."""
        assert isinstance(Node.ANALYZE_TASK.value, str)
        assert str(Node.ANALYZE_TASK) == "analyze_task"


class TestGetWsManagerOptional:
    """Tests for get_ws_manager_optional function."""

    def test_get_ws_manager_optional_success(self) -> None:
        """Test getting WebSocket manager from config."""
        mock_manager = MagicMock()
        config: dict[str, Any] = {"configurable": {"ws_manager": mock_manager}}

        result = get_ws_manager_optional(cast(RunnableConfig, config))

        assert result is mock_manager

    def test_get_ws_manager_optional_not_found(self) -> None:
        """Test returns None when WebSocket manager not in config."""
        config: dict[str, Any] = {"configurable": {}}

        result = get_ws_manager_optional(cast(RunnableConfig, config))

        assert result is None

    def test_get_ws_manager_optional_no_configurable(self) -> None:
        """Test returns None when configurable key missing."""
        config: dict[str, Any] = {}

        result = get_ws_manager_optional(cast(RunnableConfig, config))

        assert result is None


class TestGetBreakpointService:
    """Tests for get_breakpoint_service function."""

    def test_get_breakpoint_service_success(self) -> None:
        """Test getting BreakpointService from config."""
        mock_service = MagicMock()
        config: dict[str, Any] = {"configurable": {"breakpoint_service": mock_service}}

        result = get_breakpoint_service(cast(RunnableConfig, config))

        assert result is mock_service

    def test_get_breakpoint_service_not_found(self) -> None:
        """Test error when BreakpointService not in config."""
        config: dict[str, Any] = {"configurable": {}}

        with pytest.raises(RuntimeError, match="BreakpointService not found"):
            get_breakpoint_service(cast(RunnableConfig, config))


class TestGetEventBus:
    """Tests for get_event_bus function."""

    def test_get_event_bus_success(self) -> None:
        """Test getting EventBus from config."""
        mock_bus = MagicMock()
        config: dict[str, Any] = {"configurable": {"event_bus": mock_bus}}

        result = get_event_bus(cast(RunnableConfig, config))

        assert result is mock_bus

    def test_get_event_bus_not_found(self) -> None:
        """Test error when EventBus not in config."""
        config: dict[str, Any] = {"configurable": {}}

        with pytest.raises(RuntimeError, match="EventBus not found"):
            get_event_bus(cast(RunnableConfig, config))


class TestGetContainer:
    """Tests for get_container function."""

    def test_get_container_success(self) -> None:
        """Test getting container from config."""
        mock_container = MagicMock()
        config: dict[str, Any] = {"configurable": {"container": mock_container}}

        result = get_container(cast(RunnableConfig, config))

        assert result is mock_container

    def test_get_container_not_found(self) -> None:
        """Test error when container not in config."""
        config: dict[str, Any] = {"configurable": {}}

        with pytest.raises(RuntimeError, match="Container not found"):
            get_container(cast(RunnableConfig, config))

    def test_get_container_no_configurable(self) -> None:
        """Test error when configurable key missing."""
        config: dict[str, Any] = {}

        with pytest.raises(RuntimeError, match="Container not found"):
            get_container(cast(RunnableConfig, config))


class TestGetMcpExecutor:
    """Tests for get_mcp_executor function."""

    def test_get_mcp_executor_success(self) -> None:
        """Test getting MCP executor from config."""
        mock_executor = MagicMock()
        config: dict[str, Any] = {"configurable": {"mcp_executor": mock_executor}}

        result = get_mcp_executor(cast(RunnableConfig, config))

        assert result is mock_executor

    def test_get_mcp_executor_not_found(self) -> None:
        """Test returns None when executor not in config."""
        config: dict[str, Any] = {"configurable": {}}

        result = get_mcp_executor(cast(RunnableConfig, config))

        assert result is None

    def test_get_mcp_executor_no_configurable(self) -> None:
        """Test returns None when configurable missing."""
        config: dict[str, Any] = {}

        result = get_mcp_executor(cast(RunnableConfig, config))

        assert result is None


class TestCheckTaskCancelled:
    """Tests for check_task_cancelled function."""

    @pytest.mark.asyncio
    async def test_check_task_cancelled_failed_status(self) -> None:
        """Test returns True when task has FAILED status."""
        from unittest.mock import patch

        mock_session = AsyncMock()
        task_id = uuid4()

        mock_task = MagicMock()
        mock_task.status = TaskStatus.FAILED.value

        with patch("agent.graph.nodes.TaskRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_task)
            MockRepo.return_value = mock_repo

            result = await check_task_cancelled(mock_session, task_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_check_task_cancelled_completed_status(self) -> None:
        """Test returns True when task has COMPLETED status."""
        from unittest.mock import patch

        mock_session = AsyncMock()
        task_id = uuid4()

        mock_task = MagicMock()
        mock_task.status = TaskStatus.COMPLETED.value

        with patch("agent.graph.nodes.TaskRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_task)
            MockRepo.return_value = mock_repo

            result = await check_task_cancelled(mock_session, task_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_check_task_cancelled_in_progress(self) -> None:
        """Test returns False when task is IN_PROGRESS."""
        from unittest.mock import patch

        mock_session = AsyncMock()
        task_id = uuid4()

        mock_task = MagicMock()
        mock_task.status = TaskStatus.IN_PROGRESS.value

        with patch("agent.graph.nodes.TaskRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_task)
            MockRepo.return_value = mock_repo

            result = await check_task_cancelled(mock_session, task_id)

            assert result is False

    @pytest.mark.asyncio
    async def test_check_task_cancelled_pending(self) -> None:
        """Test returns False when task is PENDING."""
        from unittest.mock import patch

        mock_session = AsyncMock()
        task_id = uuid4()

        mock_task = MagicMock()
        mock_task.status = TaskStatus.PENDING.value

        with patch("agent.graph.nodes.TaskRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_task)
            MockRepo.return_value = mock_repo

            result = await check_task_cancelled(mock_session, task_id)

            assert result is False

    @pytest.mark.asyncio
    async def test_check_task_cancelled_task_not_found(self) -> None:
        """Test returns True when task does not exist."""
        from unittest.mock import patch

        mock_session = AsyncMock()
        task_id = uuid4()

        with patch("agent.graph.nodes.TaskRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=None)
            MockRepo.return_value = mock_repo

            result = await check_task_cancelled(mock_session, task_id)

            assert result is True


class TestNodeContext:
    """Tests for NodeContext class."""

    def test_from_config_success(self) -> None:
        """Test creating NodeContext from valid config."""
        mock_container = MagicMock()
        mock_event_bus = MagicMock()
        mock_session = AsyncMock()

        config: dict[str, Any] = {
            "configurable": {
                "container": mock_container,
                "event_bus": mock_event_bus,
            }
        }

        ctx = NodeContext.from_config(cast(RunnableConfig, config), mock_session)

        assert ctx.container is mock_container
        assert ctx.event_bus is mock_event_bus
        assert ctx.session is mock_session
        assert ctx.ws_manager is None
        assert ctx.mcp_executor is None

    def test_from_config_with_optional_deps(self) -> None:
        """Test creating NodeContext with optional dependencies."""
        mock_container = MagicMock()
        mock_event_bus = MagicMock()
        mock_ws_manager = MagicMock()
        mock_mcp_executor = MagicMock()
        mock_breakpoint_service = MagicMock()
        mock_session = AsyncMock()

        config: dict[str, Any] = {
            "configurable": {
                "container": mock_container,
                "event_bus": mock_event_bus,
                "ws_manager": mock_ws_manager,
                "mcp_executor": mock_mcp_executor,
                "breakpoint_service": mock_breakpoint_service,
            }
        }

        ctx = NodeContext.from_config(cast(RunnableConfig, config), mock_session)

        assert ctx.ws_manager is mock_ws_manager
        assert ctx.mcp_executor is mock_mcp_executor
        assert ctx.breakpoint_service is mock_breakpoint_service

    def test_from_config_missing_container_raises(self) -> None:
        """Test that missing container raises RuntimeError."""
        mock_event_bus = MagicMock()
        mock_session = AsyncMock()

        config: dict[str, Any] = {
            "configurable": {
                "event_bus": mock_event_bus,
            }
        }

        with pytest.raises(RuntimeError, match="Container not found"):
            NodeContext.from_config(cast(RunnableConfig, config), mock_session)

    def test_from_config_missing_event_bus_raises(self) -> None:
        """Test that missing event_bus raises RuntimeError."""
        mock_container = MagicMock()
        mock_session = AsyncMock()

        config: dict[str, Any] = {
            "configurable": {
                "container": mock_container,
            }
        }

        with pytest.raises(RuntimeError, match="EventBus not found"):
            NodeContext.from_config(cast(RunnableConfig, config), mock_session)

    def test_memory_manager_lazy_init(self) -> None:
        """Test memory manager is lazily initialized."""
        mock_container = MagicMock()
        mock_event_bus = MagicMock()
        mock_session = AsyncMock()

        config: dict[str, Any] = {
            "configurable": {
                "container": mock_container,
                "event_bus": mock_event_bus,
            }
        }

        ctx = NodeContext.from_config(cast(RunnableConfig, config), mock_session)

        # Not initialized yet
        assert ctx._memory_manager is None

        # Access triggers initialization
        _ = ctx.memory_manager
        assert ctx._memory_manager is not None

    def test_cancelled_response(self) -> None:
        """Test cancelled_response returns standard structure."""
        mock_container = MagicMock()
        mock_event_bus = MagicMock()
        mock_session = AsyncMock()

        ctx = NodeContext(mock_container, mock_event_bus, mock_session)

        result = ctx.cancelled_response("test_node")

        assert result["error"] == "Task cancelled by user"
        assert result["error_node"] == "test_node"
        assert result["task_status"] == TaskStatus.FAILED
        assert result["workflow_complete"] is True

    def test_error_response(self) -> None:
        """Test error_response returns standard structure."""
        mock_container = MagicMock()
        mock_event_bus = MagicMock()
        mock_session = AsyncMock()

        ctx = NodeContext(mock_container, mock_event_bus, mock_session)

        result = ctx.error_response("test_node", "Something went wrong")

        assert result["error"] == "Something went wrong"
        assert result["error_node"] == "test_node"

    def test_error_response_with_exception(self) -> None:
        """Test error_response handles Exception objects."""
        mock_container = MagicMock()
        mock_event_bus = MagicMock()
        mock_session = AsyncMock()

        ctx = NodeContext(mock_container, mock_event_bus, mock_session)

        result = ctx.error_response("test_node", ValueError("Invalid value"))

        assert result["error"] == "Invalid value"
        assert result["error_node"] == "test_node"

    @pytest.mark.asyncio
    async def test_check_cancelled(self) -> None:
        """Test check_cancelled delegates to check_task_cancelled."""
        from unittest.mock import patch

        mock_container = MagicMock()
        mock_event_bus = MagicMock()
        mock_session = AsyncMock()
        task_id = uuid4()

        ctx = NodeContext(mock_container, mock_event_bus, mock_session)

        mock_task = MagicMock()
        mock_task.status = TaskStatus.FAILED.value

        with patch("agent.graph.nodes.TaskRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_task)
            MockRepo.return_value = mock_repo

            result = await ctx.check_cancelled(task_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_emit_started(self) -> None:
        """Test emit_started emits correct event."""
        mock_container = MagicMock()
        mock_event_bus = MagicMock()
        mock_event_bus.emit = AsyncMock()
        mock_session = AsyncMock()

        ctx = NodeContext(mock_container, mock_event_bus, mock_session)

        session_id = uuid4()
        task_id = uuid4()
        milestone_id = uuid4()

        await ctx.emit_started(
            agent="qa",
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            message="Testing",
        )

        mock_event_bus.emit.assert_called_once()
        event = mock_event_bus.emit.call_args[0][0]
        assert event.agent == "qa"
        assert event.message == "Testing"

    @pytest.mark.asyncio
    async def test_emit_completed(self) -> None:
        """Test emit_completed emits correct event with details."""
        mock_container = MagicMock()
        mock_event_bus = MagicMock()
        mock_event_bus.emit = AsyncMock()
        mock_session = AsyncMock()

        ctx = NodeContext(mock_container, mock_event_bus, mock_session)

        session_id = uuid4()
        task_id = uuid4()
        milestone_id = uuid4()

        await ctx.emit_completed(
            agent="worker",
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            message="Done",
            details={"key": "value"},
        )

        mock_event_bus.emit.assert_called_once()
        event = mock_event_bus.emit.call_args[0][0]
        assert event.agent == "worker"
        assert event.message == "Done"
        assert event.details == {"key": "value"}
