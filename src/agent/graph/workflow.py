"""LangGraph StateGraph composition and compilation.

Builds and compiles the multi-agent workflow graph that orchestrates
the 5 specialized agents for task execution.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from langgraph.graph import END, StateGraph

from agent.container import get_container
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
from .nodes import (
    Node,
    advance_node,
    analyze_task_node,
    check_context_node,
    execute_worker_node,
    generate_prompt_node,
    select_llm_node,
    summarize_node,
    verify_qa_node,
)
from .state import AgentState

if TYPE_CHECKING:
    from langgraph.graph.graph import CompiledGraph
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


def _create_node_with_session(
    node_func: Any,
    session: AsyncSession,
) -> Any:
    """Create a node function with session bound.

    LangGraph nodes receive only state, so we need to bind
    the session as a partial argument.

    Args:
        node_func: The node function to wrap
        session: Database session to bind

    Returns:
        Partial function with session bound
    """
    return partial(node_func, session=session)


def build_workflow(session: AsyncSession) -> StateGraph[AgentState]:
    """Build the agent orchestration workflow graph.

    Flow:
        Entry -> analyze_task -> select_llm -> [generate_prompt?] -> execute_worker
             -> verify_qa -> [retry/fail/next]
             -> check_context -> [summarize?]
             -> advance -> [next_milestone/complete]

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
    graph.add_conditional_edges(
        Node.VERIFY_QA,
        route_qa_decision,
        {
            QARoute.NEXT: Node.CHECK_CONTEXT,
            QARoute.RETRY: Node.EXECUTE_WORKER,
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
            AdvanceRoute.COMPLETE: END,
            AdvanceRoute.RETRY_MILESTONE: Node.EXECUTE_WORKER,
        },
    )

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

    def __init__(self, session: AsyncSession) -> None:
        """Initialize workflow runner.

        Args:
            session: Database session for the workflow
        """
        self.session = session
        self._compiled: CompiledGraph | None = None

    async def initialize(self) -> None:
        """Initialize the container and compile the workflow.

        Must be called before run().
        """
        container = get_container()
        if not container.is_initialized:
            await container.initialize(self.session)

        self._compiled = compile_workflow(self.session)

    @property
    def graph(self) -> CompiledGraph:
        """Get the compiled graph.

        Returns:
            Compiled LangGraph workflow

        Raises:
            RuntimeError: If initialize() not called
        """
        if self._compiled is None:
            raise RuntimeError("WorkflowRunner not initialized. Call initialize() first.")
        return self._compiled

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

        Raises:
            RuntimeError: If initialize() not called
        """
        if self._compiled is None:
            await self.initialize()

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
            "needs_compression": False,
            "workflow_complete": False,
            "should_continue": True,
        }

        logger.info(
            "workflow_started",
            session_id=str(session_id),
            task_id=str(task_id),
        )

        # Run workflow
        final_state: AgentState = await self.graph.ainvoke(initial_state)

        logger.info(
            "workflow_finished",
            task_id=str(task_id),
            status=final_state.get("task_status"),
            error=final_state.get("error"),
        )

        return final_state
