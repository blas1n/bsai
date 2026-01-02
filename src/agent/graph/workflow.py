"""LangGraph StateGraph composition and compilation.

Builds and compiles the multi-agent workflow graph that orchestrates
the 6 specialized agents for task execution.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from langgraph.graph import END, StateGraph

from agent.container import lifespan
from agent.db.models.enums import TaskStatus

from .edges import (
    AdvanceRoute,
    CompressionRoute,
    PromptRoute,
    QARoute,
    route_advance,
    route_qa_decision,
    should_compress_context,
    should_use_meta_prompter,
)
from .nodes import Node
from .nodes.advance import advance_node
from .nodes.analyze import analyze_task_node
from .nodes.context import check_context_node, summarize_node
from .nodes.execute import execute_worker_node
from .nodes.llm import generate_prompt_node, select_llm_node
from .nodes.qa import verify_qa_node
from .nodes.response import generate_response_node
from .state import AgentState

if TYPE_CHECKING:
    from langgraph.graph.graph import CompiledGraph
    from sqlalchemy.ext.asyncio import AsyncSession

    from agent.api.websocket.manager import ConnectionManager

logger = structlog.get_logger()


def _create_node_with_session(
    node_func: Callable[..., Any],
    session: AsyncSession,
) -> Callable[..., Any]:
    """Create a node function with session bound.

    LangGraph nodes receive (state, config), so we wrap the original
    node function to inject the session as the third argument.

    Args:
        node_func: The node function to wrap
        session: Database session to bind

    Returns:
        Wrapped async function compatible with LangGraph
    """
    from langchain_core.runnables import RunnableConfig

    async def wrapper(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result: dict[str, Any] = await node_func(state, config, session)
        return result

    # Preserve the original function name for debugging
    wrapper.__name__ = node_func.__name__
    return wrapper


def build_workflow(session: AsyncSession) -> StateGraph[AgentState]:
    """Build the agent orchestration workflow graph.

    Flow:
        Entry -> analyze_task -> select_llm -> [generate_prompt?] -> execute_worker
             -> verify_qa -> [retry/fail/next]
             -> check_context -> [summarize?]
             -> advance -> [next_milestone/generate_response/complete]
             -> generate_response -> END

    Args:
        session: Database session for node operations

    Returns:
        Configured StateGraph (not yet compiled)
    """
    # Create graph with AgentState
    graph: StateGraph[AgentState] = StateGraph(AgentState)

    # Node function mapping
    node_functions = {
        Node.ANALYZE_TASK: analyze_task_node,
        Node.SELECT_LLM: select_llm_node,
        Node.GENERATE_PROMPT: generate_prompt_node,
        Node.EXECUTE_WORKER: execute_worker_node,
        Node.VERIFY_QA: verify_qa_node,
        Node.CHECK_CONTEXT: check_context_node,
        Node.SUMMARIZE: summarize_node,
        Node.ADVANCE: advance_node,
        Node.GENERATE_RESPONSE: generate_response_node,
    }

    # Add all nodes with session bound
    for node, func in node_functions.items():
        graph.add_node(node, _create_node_with_session(func, session))

    # Set entry point
    graph.set_entry_point(Node.ANALYZE_TASK)

    # Add edges from analyze_task
    graph.add_edge(Node.ANALYZE_TASK, Node.SELECT_LLM)

    # Add conditional edge for MetaPrompter (skip for TRIVIAL/SIMPLE)
    graph.add_conditional_edges(
        Node.SELECT_LLM,
        should_use_meta_prompter,
        {
            PromptRoute.GENERATE: Node.GENERATE_PROMPT,
            PromptRoute.SKIP: Node.EXECUTE_WORKER,
        },
    )

    # Edge from generate_prompt to execute_worker
    graph.add_edge(Node.GENERATE_PROMPT, Node.EXECUTE_WORKER)

    # Edge from execute_worker to verify_qa
    graph.add_edge(Node.EXECUTE_WORKER, Node.VERIFY_QA)

    # Conditional edges from verify_qa based on QA decision
    # NOTE: RETRY also goes to ADVANCE first to increment retry_count
    # then ADVANCE routes back to EXECUTE_WORKER via RETRY_MILESTONE
    graph.add_conditional_edges(
        Node.VERIFY_QA,
        route_qa_decision,
        {
            QARoute.NEXT: Node.CHECK_CONTEXT,
            QARoute.RETRY: Node.ADVANCE,
            QARoute.FAIL: Node.ADVANCE,
        },
    )

    # Conditional edges for context compression
    graph.add_conditional_edges(
        Node.CHECK_CONTEXT,
        should_compress_context,
        {
            CompressionRoute.SUMMARIZE: Node.SUMMARIZE,
            CompressionRoute.SKIP: Node.ADVANCE,
        },
    )

    # Edge from summarize to advance
    graph.add_edge(Node.SUMMARIZE, Node.ADVANCE)

    # Conditional edges from advance
    graph.add_conditional_edges(
        Node.ADVANCE,
        route_advance,
        {
            AdvanceRoute.NEXT_MILESTONE: Node.SELECT_LLM,
            AdvanceRoute.COMPLETE: Node.GENERATE_RESPONSE,
            AdvanceRoute.RETRY_MILESTONE: Node.EXECUTE_WORKER,
        },
    )

    graph.add_edge(Node.GENERATE_RESPONSE, END)

    logger.info("workflow_graph_built")

    return graph


def compile_workflow(
    session: AsyncSession,
    checkpointer: object | None = None,
) -> CompiledGraph:
    """Compile the workflow graph.

    Args:
        session: Database session for node operations
        checkpointer: Optional checkpointer for state persistence

    Returns:
        Compiled graph ready for execution
    """
    graph = build_workflow(session)

    compile_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    compiled = graph.compile(**compile_kwargs)

    logger.info("workflow_compiled")

    return compiled


class WorkflowRunner:
    """High-level workflow runner with session management.

    Handles database session lifecycle and provides a clean API
    for executing workflows.
    """

    def __init__(
        self,
        session: AsyncSession,
        ws_manager: ConnectionManager | None = None,
    ) -> None:
        """Initialize workflow runner.

        Args:
            session: Database session for the workflow
            ws_manager: Optional WebSocket manager for real-time updates
        """
        self.session = session
        self.ws_manager = ws_manager

    async def run(
        self,
        session_id: str | UUID,
        task_id: str | UUID,
        original_request: str,
        max_context_tokens: int = 100000,
    ) -> AgentState:
        """Run workflow for a task.

        Args:
            session_id: Session UUID (string or UUID)
            task_id: Task UUID (string or UUID)
            original_request: User's original request
            max_context_tokens: Maximum context window

        Returns:
            Final workflow state
        """
        # Ensure UUIDs
        if isinstance(session_id, str):
            session_id = UUID(session_id)
        if isinstance(task_id, str):
            task_id = UUID(task_id)

        # Build initial state
        initial_state: AgentState = {
            "session_id": session_id,
            "task_id": task_id,
            "original_request": original_request,
            "task_status": TaskStatus.PENDING,
            "milestones": [],
            "current_milestone_index": 0,
            "retry_count": 0,
            "context_messages": [],
            "current_context_tokens": 0,
            "max_context_tokens": max_context_tokens,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": "0",
            "needs_compression": False,
            "workflow_complete": False,
            "should_continue": True,
        }

        logger.info(
            "workflow_started",
            session_id=str(session_id),
            task_id=str(task_id),
        )

        async with lifespan(self.session) as container:
            compiled = compile_workflow(self.session)

            final_state: AgentState = await compiled.ainvoke(
                initial_state,
                config={
                    "recursion_limit": 100,
                    "configurable": {
                        "ws_manager": self.ws_manager,
                        "container": container,
                    },
                },
            )

        logger.info(
            "workflow_finished",
            task_id=str(task_id),
            status=final_state.get("task_status"),
            error=final_state.get("error"),
        )

        return final_state
