"""LangGraph node functions for agent orchestration.

Each node:
1. Receives AgentState, database session, and RunnableConfig
2. Calls appropriate agent method
3. Returns partial state update (immutable)
4. Handles errors gracefully
5. Emits events via EventBus for real-time UI updates

All nodes follow the pattern of returning partial state dicts
that LangGraph merges with the existing state.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.websocket.manager import ConnectionManager
from agent.container import ContainerState
from agent.db.models.enums import TaskStatus
from agent.db.repository.task_repo import TaskRepository
from agent.events import EventBus
from agent.mcp.executor import McpToolExecutor
from agent.services import BreakpointService

_logger = structlog.get_logger()


class Node(StrEnum):
    """Workflow node names."""

    ANALYZE_TASK = "analyze_task"
    SELECT_LLM = "select_llm"
    GENERATE_PROMPT = "generate_prompt"
    EXECUTE_WORKER = "execute_worker"
    QA_BREAKPOINT = "qa_breakpoint"
    VERIFY_QA = "verify_qa"
    CHECK_CONTEXT = "check_context"
    SUMMARIZE = "summarize"
    ADVANCE = "advance"
    GENERATE_RESPONSE = "generate_response"


def get_breakpoint_service(config: RunnableConfig) -> BreakpointService:
    """Extract BreakpointService from config.

    Used for breakpoint state management (enable/disable, pause tracking).

    Args:
        config: LangGraph RunnableConfig

    Returns:
        BreakpointService instance

    Raises:
        RuntimeError: If breakpoint_service not in config
    """
    configurable = config.get("configurable", {})
    breakpoint_service: BreakpointService | None = configurable.get("breakpoint_service")
    if breakpoint_service is None:
        msg = "BreakpointService not found in config. Ensure workflow is run with breakpoint_service in configurable."
        raise RuntimeError(msg)
    return breakpoint_service


def get_container(config: RunnableConfig) -> ContainerState:
    """Extract container from config.

    Args:
        config: LangGraph RunnableConfig

    Returns:
        ContainerState with initialized dependencies

    Raises:
        RuntimeError: If container not in config
    """
    configurable = config.get("configurable", {})
    container: ContainerState | None = configurable.get("container")
    if container is None:
        raise RuntimeError(
            "Container not found in config. Ensure workflow is run with lifespan context."
        )
    return container


def get_mcp_executor(config: RunnableConfig) -> McpToolExecutor | None:
    """Extract MCP tool executor from config.

    Args:
        config: LangGraph RunnableConfig

    Returns:
        McpToolExecutor if available, None otherwise
    """
    configurable = config.get("configurable", {})
    return configurable.get("mcp_executor")


def get_event_bus(config: RunnableConfig) -> EventBus:
    """Extract EventBus from config.

    Args:
        config: LangGraph RunnableConfig

    Returns:
        EventBus instance

    Raises:
        RuntimeError: If event_bus not in config
    """
    configurable = config.get("configurable", {})
    event_bus: EventBus | None = configurable.get("event_bus")
    if event_bus is None:
        msg = "EventBus not found in config. Ensure workflow is run with event_bus in configurable."
        raise RuntimeError(msg)
    return event_bus


def get_ws_manager_optional(config: RunnableConfig) -> ConnectionManager | None:
    """Extract WebSocket manager from config (optional).

    Used only for MCP stdio tool coordination. Returns None if not available,
    which means MCP stdio tools will not be supported but HTTP/SSE tools will work.

    Args:
        config: LangGraph RunnableConfig

    Returns:
        ConnectionManager instance or None if not available
    """
    configurable = config.get("configurable", {})
    return configurable.get("ws_manager")


async def check_task_cancelled(
    session: AsyncSession,
    task_id: UUID,
) -> bool:
    """Check if task has been cancelled.

    Args:
        session: Database session
        task_id: Task UUID to check

    Returns:
        True if task is cancelled/failed, False otherwise
    """
    task_repo = TaskRepository(session)
    task = await task_repo.get_by_id(task_id)

    if task is None:
        _logger.warning("check_task_cancelled_not_found", task_id=str(task_id))
        return True  # Treat missing task as cancelled

    # Only treat FAILED or COMPLETED status as cancelled/finished
    # PENDING and IN_PROGRESS are normal running states
    if task.status in (TaskStatus.FAILED.value, TaskStatus.COMPLETED.value):
        _logger.info(
            "task_cancelled_detected",
            task_id=str(task_id),
            status=task.status,
        )
        return True

    return False


__all__ = [
    "Node",
    "get_breakpoint_service",
    "get_container",
    "get_mcp_executor",
    "get_event_bus",
    "get_ws_manager_optional",
    "check_task_cancelled",
]
