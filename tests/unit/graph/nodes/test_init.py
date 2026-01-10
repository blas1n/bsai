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
    check_task_cancelled,
    get_container,
    get_mcp_executor,
    get_ws_manager,
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


class TestGetWsManager:
    """Tests for get_ws_manager function."""

    def test_get_ws_manager_success(self) -> None:
        """Test getting WebSocket manager from config."""
        mock_manager = MagicMock()
        config: dict[str, Any] = {"configurable": {"ws_manager": mock_manager}}

        result = get_ws_manager(cast(RunnableConfig, config))

        assert result is mock_manager

    def test_get_ws_manager_not_found(self) -> None:
        """Test error when WebSocket manager not in config."""
        config: dict[str, Any] = {"configurable": {}}

        with pytest.raises(RuntimeError, match="WebSocket manager not found"):
            get_ws_manager(cast(RunnableConfig, config))

    def test_get_ws_manager_no_configurable(self) -> None:
        """Test error when configurable key missing."""
        config: dict[str, Any] = {}

        with pytest.raises(RuntimeError, match="WebSocket manager not found"):
            get_ws_manager(cast(RunnableConfig, config))


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
