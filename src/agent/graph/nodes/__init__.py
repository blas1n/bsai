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

from langchain_core.runnables import RunnableConfig

from agent.container import ContainerState

from .advance import advance_node
from .analyze import analyze_task_node
from .context import check_context_node, summarize_node
from .execute import execute_worker_node
from .llm import generate_prompt_node, select_llm_node
from .qa import verify_qa_node
from .response import generate_response_node

if TYPE_CHECKING:
    from agent.api.websocket.manager import ConnectionManager


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


def get_ws_manager(config: RunnableConfig) -> ConnectionManager | None:
    """Extract WebSocket manager from config.

    Args:
        config: LangGraph RunnableConfig

    Returns:
        ConnectionManager if present, None otherwise
    """
    configurable = config.get("configurable", {})
    return configurable.get("ws_manager")


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
    container = configurable.get("container")
    if container is None:
        raise RuntimeError(
            "Container not found in config. Ensure workflow is run with lifespan context."
        )
    return container


__all__ = [
    "Node",
    "get_ws_manager",
    "get_container",
    "analyze_task_node",
    "select_llm_node",
    "generate_prompt_node",
    "execute_worker_node",
    "verify_qa_node",
    "check_context_node",
    "summarize_node",
    "advance_node",
    "generate_response_node",
]
