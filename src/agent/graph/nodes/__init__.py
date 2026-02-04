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
from agent.events import AgentActivityEvent, AgentStatus, EventBus, EventType
from agent.mcp.executor import McpToolExecutor
from agent.memory import LongTermMemoryManager
from agent.services import BreakpointService

_logger = structlog.get_logger()


class NodeContext:
    """Unified context for node dependencies.

    Reduces boilerplate by providing a single object that holds all
    common dependencies needed by workflow nodes.

    Usage:
        ctx = NodeContext.from_config(config, session)
        await ctx.emit_started("qa", milestone_id, "Validating output")
        # ... do work ...
        await ctx.emit_completed("qa", milestone_id, "Validation complete", details)
    """

    def __init__(
        self,
        container: ContainerState,
        event_bus: EventBus,
        session: AsyncSession,
        ws_manager: ConnectionManager | None = None,
        mcp_executor: McpToolExecutor | None = None,
        breakpoint_service: BreakpointService | None = None,
    ) -> None:
        """Initialize node context with dependencies.

        Args:
            container: Dependency container with llm_client, router, etc.
            event_bus: EventBus for emitting agent events
            session: Database session
            ws_manager: Optional WebSocket manager for MCP stdio
            mcp_executor: Optional MCP tool executor
            breakpoint_service: Optional breakpoint service
        """
        self.container = container
        self.event_bus = event_bus
        self.session = session
        self.ws_manager = ws_manager
        self.mcp_executor = mcp_executor
        self.breakpoint_service = breakpoint_service
        self._memory_manager: LongTermMemoryManager | None = None

    @classmethod
    def from_config(
        cls,
        config: RunnableConfig,
        session: AsyncSession,
    ) -> NodeContext:
        """Create NodeContext from LangGraph config.

        Args:
            config: LangGraph RunnableConfig
            session: Database session

        Returns:
            Initialized NodeContext
        """
        configurable = config.get("configurable", {})
        container = configurable.get("container")
        if container is None:
            raise RuntimeError(
                "Container not found in config. Ensure workflow is run with lifespan context."
            )

        event_bus = configurable.get("event_bus")
        if event_bus is None:
            raise RuntimeError(
                "EventBus not found in config. Ensure workflow is run with event_bus in configurable."
            )

        return cls(
            container=container,
            event_bus=event_bus,
            session=session,
            ws_manager=configurable.get("ws_manager"),
            mcp_executor=configurable.get("mcp_executor"),
            breakpoint_service=configurable.get("breakpoint_service"),
        )

    @property
    def memory_manager(self) -> LongTermMemoryManager:
        """Lazy-initialize and return memory manager."""
        if self._memory_manager is None:
            self._memory_manager = LongTermMemoryManager(
                session=self.session,
                embedding_service=self.container.embedding_service,
                prompt_manager=self.container.prompt_manager,
            )
        return self._memory_manager

    async def check_cancelled(self, task_id: UUID) -> bool:
        """Check if task has been cancelled.

        Args:
            task_id: Task UUID to check

        Returns:
            True if task is cancelled/failed, False otherwise
        """
        return await check_task_cancelled(self.session, task_id)

    async def emit_started(
        self,
        agent: str,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
        message: str,
        sequence_number: int = 0,
    ) -> None:
        """Emit agent started event.

        Args:
            agent: Agent name (e.g., "qa", "worker", "conductor")
            session_id: Session UUID
            task_id: Task UUID
            milestone_id: Milestone UUID (use task_id if no milestone)
            message: Status message
            sequence_number: Optional sequence number
        """
        await self.event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_STARTED,
                session_id=session_id,
                task_id=task_id,
                milestone_id=milestone_id,
                sequence_number=sequence_number,
                agent=agent,
                status=AgentStatus.STARTED,
                message=message,
            )
        )

    async def emit_completed(
        self,
        agent: str,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
        message: str,
        sequence_number: int = 0,
        details: dict | None = None,
    ) -> None:
        """Emit agent completed event.

        Args:
            agent: Agent name
            session_id: Session UUID
            task_id: Task UUID
            milestone_id: Milestone UUID (use task_id if no milestone)
            message: Completion message
            sequence_number: Optional sequence number
            details: Optional details dictionary
        """
        await self.event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_COMPLETED,
                session_id=session_id,
                task_id=task_id,
                milestone_id=milestone_id,
                sequence_number=sequence_number,
                agent=agent,
                status=AgentStatus.COMPLETED,
                message=message,
                details=details,
            )
        )

    def cancelled_response(self, node_name: str) -> dict:
        """Return standard cancelled task response.

        Args:
            node_name: Name of the node returning cancellation

        Returns:
            Standard cancellation state update
        """
        return {
            "error": "Task cancelled by user",
            "error_node": node_name,
            "task_status": TaskStatus.FAILED,
            "workflow_complete": True,
        }

    def error_response(self, node_name: str, error: str | Exception) -> dict:
        """Return standard error response.

        Args:
            node_name: Name of the node that errored
            error: Error message or exception

        Returns:
            Standard error state update
        """
        return {
            "error": str(error),
            "error_node": node_name,
        }


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
    TASK_SUMMARY = "task_summary"
    GENERATE_RESPONSE = "generate_response"
    REPLAN = "replan"  # Dynamic plan modification
    RECOVERY = "recovery"  # Graceful failure recovery
    PLAN_REVIEW = "plan_review"  # Plan review breakpoint (Human-in-the-Loop)
    EXECUTION_BREAKPOINT = "execution_breakpoint"  # Execution breakpoint for task-level pausing


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


def get_memory_manager(
    config: RunnableConfig,
    session: AsyncSession,
) -> LongTermMemoryManager:
    """Create a LongTermMemoryManager using container dependencies.

    Uses the EmbeddingService and PromptManager from the container
    to create a memory manager for the given database session.

    Args:
        config: LangGraph RunnableConfig
        session: Database session for this request

    Returns:
        LongTermMemoryManager instance
    """
    container = get_container(config)
    return LongTermMemoryManager(
        session=session,
        embedding_service=container.embedding_service,
        prompt_manager=container.prompt_manager,
    )


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


# Import plan review node functions after all definitions to avoid circular imports
# These are re-exported for convenient access from the nodes package
# Import execution breakpoint node functions
from agent.graph.nodes.execution_breakpoint import (  # noqa: E402
    execution_breakpoint,
    execution_breakpoint_router,
    get_current_progress,
    resume_execution,
)
from agent.graph.nodes.plan_review import (  # noqa: E402
    plan_review_breakpoint,
    plan_review_router,
    resume_after_approval,
    resume_after_rejection,
    resume_after_revision,
)

__all__ = [
    "Node",
    "NodeContext",
    "get_breakpoint_service",
    "get_container",
    "get_mcp_executor",
    "get_event_bus",
    "get_ws_manager_optional",
    "get_memory_manager",
    "check_task_cancelled",
    # Plan review breakpoint
    "plan_review_breakpoint",
    "plan_review_router",
    "resume_after_approval",
    "resume_after_revision",
    "resume_after_rejection",
    # Execution breakpoint
    "execution_breakpoint",
    "execution_breakpoint_router",
    "resume_execution",
    "get_current_progress",
]
