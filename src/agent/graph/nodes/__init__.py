"""LangGraph node functions for agent orchestration.

Each node:
1. Receives AgentState, database session, and RunnableConfig
2. Calls appropriate agent method
3. Returns partial state update (immutable)
4. Handles errors gracefully
5. Broadcasts WebSocket notifications for real-time UI updates

All nodes follow the pattern of returning partial state dicts
that LangGraph merges with the existing state.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from agent.container import ContainerState

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from agent.api.websocket.manager import ConnectionManager
    from agent.mcp.executor import McpToolExecutor


class Node(StrEnum):
    """Workflow node names."""

    ANALYZE_TASK = "analyze_task"
    SELECT_LLM = "select_llm"
    GENERATE_PROMPT = "generate_prompt"
    EXECUTE_WORKER = "execute_worker"
    VERIFY_QA = "verify_qa"
    CHECK_CONTEXT = "check_context"
    SUMMARIZE = "summarize"
    ADVANCE = "advance"
    GENERATE_RESPONSE = "generate_response"


def get_ws_manager(config: RunnableConfig) -> ConnectionManager:
    """Extract WebSocket manager from config.

    Args:
        config: LangGraph RunnableConfig

    Returns:
        ConnectionManager instance

    Raises:
        RuntimeError: If ws_manager not in config
    """
    configurable = config.get("configurable", {})
    ws_manager = configurable.get("ws_manager")
    if ws_manager is None:
        msg = "WebSocket manager not found in config. Ensure workflow is run with proper context."
        raise RuntimeError(msg)
    return ws_manager


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


__all__ = [
    "Node",
    "get_ws_manager",
    "get_container",
    "get_mcp_executor",
]
