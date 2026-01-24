"""LangGraph StateGraph composition and compilation.

Builds and compiles the multi-agent workflow graph that orchestrates
the 8 specialized agents for task execution.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.websocket.manager import ConnectionManager
from agent.cache import SessionCache
from agent.container import lifespan
from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.db.repository.memory_snapshot_repo import MemorySnapshotRepository
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.db.repository.session_repo import SessionRepository
from agent.db.repository.task_repo import TaskRepository
from agent.events import EventBus
from agent.llm import ChatMessage
from agent.services import BreakpointService
from agent.tracing import get_langfuse_callback, get_langfuse_tracer

from .checkpointer import get_checkpointer
from .edges import (
    AdvanceRoute,
    CompressionRoute,
    PromptRoute,
    QARoute,
    RecoveryRoute,
    route_advance,
    route_qa_decision,
    route_recovery,
    should_compress_context,
    should_use_meta_prompter,
)
from .nodes import Node
from .nodes.advance import advance_node
from .nodes.analyze import analyze_task_node
from .nodes.breakpoint import qa_breakpoint_node
from .nodes.context import check_context_node, summarize_node
from .nodes.execute import execute_worker_node
from .nodes.llm import generate_prompt_node, select_llm_node
from .nodes.qa import verify_qa_node
from .nodes.recovery import recovery_node
from .nodes.replan import replan_node
from .nodes.response import generate_response_node
from .nodes.task_summary import task_summary_node
from .state import AgentState, MilestoneData

if TYPE_CHECKING:
    from langchain_core.callbacks import BaseCallbackHandler


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""

    state: AgentState
    interrupted: bool = False
    interrupt_node: str | None = None


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

    async def wrapper(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result: dict[str, Any] = await node_func(state, config, session)
        return result

    # Preserve the original function name for debugging
    wrapper.__name__ = node_func.__name__
    return wrapper


def build_workflow(session: AsyncSession) -> StateGraph[AgentState]:
    """Build the agent orchestration workflow graph.

    Flow:
        Entry -> analyze_task -> select_llm -> [generate_prompt?]
             -> execute_worker -> verify_qa -> [retry/fail/next/replan]
             -> [replan -> select_llm]  (ReAct dynamic replanning)
             -> check_context -> [summarize?]
             -> advance -> [next_milestone/task_summary/retry]
             -> task_summary -> generate_response -> END

    The task_summary node generates a summary of all milestones for:
    - Responder to create a complete user response
    - Next task's Conductor to understand previous work

    The replan node enables dynamic plan modification based on
    observations from Worker execution and plan viability assessments.

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
        Node.QA_BREAKPOINT: qa_breakpoint_node,
        Node.VERIFY_QA: verify_qa_node,
        Node.CHECK_CONTEXT: check_context_node,
        Node.SUMMARIZE: summarize_node,
        Node.ADVANCE: advance_node,
        Node.TASK_SUMMARY: task_summary_node,
        Node.GENERATE_RESPONSE: generate_response_node,
        Node.REPLAN: replan_node,
        Node.RECOVERY: recovery_node,
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

    # Edge from execute_worker to qa_breakpoint (Human-in-the-Loop checkpoint)
    graph.add_edge(Node.EXECUTE_WORKER, Node.QA_BREAKPOINT)

    # Edge from qa_breakpoint to verify_qa
    graph.add_edge(Node.QA_BREAKPOINT, Node.VERIFY_QA)

    # Conditional edges from verify_qa based on QA decision
    # NOTE: RETRY also goes to ADVANCE first to increment retry_count
    # then ADVANCE routes back to EXECUTE_WORKER via RETRY_MILESTONE
    # REPLAN triggers dynamic plan modification when QA detects plan viability issues
    # FAIL now routes to RECOVERY for graceful failure handling
    graph.add_conditional_edges(
        Node.VERIFY_QA,
        route_qa_decision,
        {
            QARoute.NEXT: Node.CHECK_CONTEXT,
            QARoute.RETRY: Node.ADVANCE,
            QARoute.FAIL: Node.RECOVERY,
            QARoute.REPLAN: Node.REPLAN,
        },
    )

    graph.add_edge(Node.REPLAN, Node.SELECT_LLM)

    # Conditional edges from recovery node
    # - STRATEGY_RETRY: Try a completely different approach (back to select_llm)
    # - FAILURE_REPORT: Generate detailed failure report (to task_summary -> response)
    graph.add_conditional_edges(
        Node.RECOVERY,
        route_recovery,
        {
            RecoveryRoute.STRATEGY_RETRY: Node.SELECT_LLM,
            RecoveryRoute.FAILURE_REPORT: Node.TASK_SUMMARY,
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
            AdvanceRoute.COMPLETE: Node.TASK_SUMMARY,
            AdvanceRoute.RETRY_MILESTONE: Node.EXECUTE_WORKER,
        },
    )

    graph.add_edge(Node.TASK_SUMMARY, Node.GENERATE_RESPONSE)
    graph.add_edge(Node.GENERATE_RESPONSE, END)

    logger.info("workflow_graph_built")

    return graph


def compile_workflow(
    session: AsyncSession,
    checkpointer: object | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
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
    for executing workflows. Includes Langfuse tracing integration
    for observability and debugging.
    """

    def __init__(
        self,
        session: AsyncSession,
        ws_manager: ConnectionManager,
        cache: SessionCache,
        event_bus: EventBus,
        breakpoint_service: BreakpointService,
    ) -> None:
        """Initialize workflow runner.

        Args:
            session: Database session for the workflow
            ws_manager: WebSocket manager for MCP stdio tools
            cache: Session cache for context persistence
            event_bus: EventBus for event-driven notifications
            breakpoint_service: BreakpointService for HITL workflows
        """
        self.session = session
        self.ws_manager = ws_manager
        self.cache = cache
        self.event_bus = event_bus
        self.breakpoint_service = breakpoint_service
        self._tracer = get_langfuse_tracer()

    async def _load_previous_milestones(
        self,
        session_id: UUID,
    ) -> tuple[list[MilestoneData], int]:
        """Load previous milestones from session for continuity.

        Args:
            session_id: Session UUID

        Returns:
            Tuple of (milestones_data, next_sequence_number)
        """
        # Map QADecision values to MilestoneStatus
        status_mapping = {
            "pass": MilestoneStatus.PASSED,
            "retry": MilestoneStatus.IN_PROGRESS,
            "fail": MilestoneStatus.FAILED,
        }

        milestone_repo = MilestoneRepository(self.session)
        db_milestones = await milestone_repo.get_by_session_id(session_id)

        milestones: list[MilestoneData] = []
        for m in db_milestones:
            # Convert DB model to MilestoneData
            complexity = m.complexity
            if isinstance(complexity, str):
                complexity = TaskComplexity(complexity)

            status = m.status
            if isinstance(status, str):
                # Try mapping from QADecision values first, then MilestoneStatus
                status = status_mapping.get(status) or MilestoneStatus(status)

            milestones.append(
                MilestoneData(
                    id=m.id,
                    description=m.description,
                    complexity=complexity,
                    acceptance_criteria=m.acceptance_criteria or "",
                    status=status,
                    selected_model=m.selected_llm or None,
                    generated_prompt=None,
                    worker_output=m.worker_output,
                    qa_feedback=m.qa_result,
                    retry_count=m.retry_count,
                )
            )

        # Get max sequence number for next milestone numbering
        max_seq = await milestone_repo.get_max_sequence_for_session(session_id)

        logger.info(
            "previous_milestones_loaded",
            session_id=str(session_id),
            milestone_count=len(milestones),
            max_sequence=max_seq,
        )

        return milestones, max_seq

    async def _load_previous_context(
        self,
        session_id: UUID,
    ) -> tuple[list[ChatMessage], str | None, int]:
        """Load previous conversation context from cache or memory snapshot.

        Args:
            session_id: Session UUID

        Returns:
            Tuple of (context_messages, context_summary, estimated_tokens)
        """
        context_messages: list[ChatMessage] = []
        context_summary: str | None = None
        token_count = 0

        # Try cache first
        cached = await self.cache.get_cached_context(session_id)
        if cached:
            messages_data = cached.get("messages", [])
            context_messages = [
                ChatMessage(role=m["role"], content=m["content"]) for m in messages_data
            ]
            context_summary = cached.get("summary")
            token_count = cached["token_count"]
            logger.info(
                "context_loaded_from_cache",
                session_id=str(session_id),
                message_count=len(context_messages),
                has_summary=context_summary is not None,
                token_count=token_count,
            )
            return context_messages, context_summary, token_count

        # Fall back to memory snapshot
        snapshot_repo = MemorySnapshotRepository(self.session)
        snapshot = await snapshot_repo.get_latest_snapshot(session_id)
        if snapshot:
            context_summary = snapshot.compressed_context
            token_count = snapshot.token_count
            # Add summary as system context
            context_messages = [
                ChatMessage(
                    role="system",
                    content=f"Previous conversation summary:\n{context_summary}",
                )
            ]
            logger.info(
                "context_loaded_from_snapshot",
                session_id=str(session_id),
                snapshot_id=str(snapshot.id),
                token_count=token_count,
            )

        return context_messages, context_summary, token_count

    async def _load_previous_task_handover(
        self,
        session_id: UUID,
    ) -> str | None:
        """Load handover context from the previous completed task.

        This provides Conductor with context about what was done in the
        previous task, including milestones completed and artifacts created.

        Args:
            session_id: Session UUID

        Returns:
            Handover context string or None if no previous task
        """
        task_repo = TaskRepository(self.session)
        handover = await task_repo.get_previous_task_handover(session_id)

        if handover:
            logger.info(
                "previous_task_handover_loaded",
                session_id=str(session_id),
                handover_length=len(handover),
            )
        else:
            logger.info(
                "no_previous_task_handover",
                session_id=str(session_id),
            )

        return handover

    def get_trace_url(self, task_id: str | UUID) -> str:
        """Get the Langfuse trace URL for a task.

        Args:
            task_id: The task UUID

        Returns:
            URL to view the trace in Langfuse UI, or empty string if tracing is disabled
        """
        return self._tracer.get_trace_url(task_id)

    async def run(
        self,
        session_id: str | UUID,
        task_id: str | UUID,
        original_request: str,
        max_context_tokens: int = 100000,
        breakpoint_enabled: bool = False,
        breakpoint_nodes: list[str] | None = None,
    ) -> WorkflowResult:
        """Run workflow for a task.

        Integrates with Langfuse for tracing and observability when enabled.
        The trace URL is included in the returned state for frontend linking.

        Args:
            session_id: Session UUID (string or UUID)
            task_id: Task UUID (string or UUID)
            original_request: User's original request
            max_context_tokens: Maximum context window
            breakpoint_enabled: Whether breakpoints are enabled
            breakpoint_nodes: List of node names to pause at

        Returns:
            WorkflowResult containing state and interrupt status
        """
        # Ensure UUIDs
        if isinstance(session_id, str):
            session_id = UUID(session_id)
        if isinstance(task_id, str):
            task_id = UUID(task_id)

        # Load user_id from session
        session_repo = SessionRepository(self.session)
        session = await session_repo.get_by_id(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        user_id = session.user_id or "unknown"

        # Load previous context and milestones from same session
        context_messages, context_summary, context_tokens = await self._load_previous_context(
            session_id
        )
        previous_milestones, max_sequence = await self._load_previous_milestones(session_id)

        # Load handover context from previous completed task (if any)
        previous_task_handover = await self._load_previous_task_handover(session_id)
        if previous_task_handover:
            # Prepend handover context for Conductor to reference
            handover_message = ChatMessage(
                role="system",
                content=f"Context from previous task in this session:\n{previous_task_handover}",
            )
            context_messages = [handover_message] + context_messages

        # Create Langfuse callback handler for tracing
        langfuse_callback = get_langfuse_callback(
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            trace_name=f"task-{task_id}",
            metadata={
                "original_request": original_request[:500],
                "previous_milestone_count": len(previous_milestones),
            },
            tags=["bsai", "langgraph", "multi-agent"],
        )
        trace_url = self.get_trace_url(task_id)

        # Build initial state with previous context and milestones
        initial_state: AgentState = {
            "session_id": session_id,
            "task_id": task_id,
            "user_id": user_id,
            "original_request": original_request,
            "task_status": TaskStatus.PENDING,
            "milestones": previous_milestones,
            "current_milestone_index": len(previous_milestones),
            "milestone_sequence_offset": max_sequence,
            "retry_count": 0,
            "context_messages": context_messages,
            "context_summary": context_summary,
            "current_context_tokens": context_tokens,
            "max_context_tokens": max_context_tokens,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": "0",
            "needs_compression": False,
            "workflow_complete": False,
            "should_continue": True,
            "breakpoint_enabled": breakpoint_enabled,
            "breakpoint_nodes": breakpoint_nodes or ["qa_breakpoint"],
        }

        logger.info(
            "workflow_started",
            session_id=str(session_id),
            task_id=str(task_id),
            has_previous_context=len(context_messages) > 0,
            previous_milestone_count=len(previous_milestones),
            has_handover_context=previous_task_handover is not None,
            trace_url=trace_url,
            tracing_enabled=langfuse_callback is not None,
        )

        async with lifespan(self.session) as container:
            # Get checkpointer for state persistence
            async with get_checkpointer() as checkpointer:
                compiled = compile_workflow(self.session, checkpointer=checkpointer)

                # Build config with optional Langfuse callback
                callbacks: list[BaseCallbackHandler] = []
                if langfuse_callback:
                    callbacks.append(langfuse_callback)

                # Thread ID for checkpointing (unique per task)
                thread_id = str(task_id)

                config: RunnableConfig = {
                    "recursion_limit": 100,
                    "callbacks": callbacks,
                    "configurable": {
                        "thread_id": thread_id,
                        "ws_manager": self.ws_manager,
                        "container": container,
                        "trace_url": trace_url,
                        "event_bus": self.event_bus,
                        "breakpoint_service": self.breakpoint_service,
                    },
                }

                final_state: AgentState = cast(
                    AgentState,
                    await compiled.ainvoke(initial_state, config=config),
                )

                # Check if workflow was interrupted (paused at breakpoint)
                graph_state = await compiled.aget_state(config)
                interrupted = bool(graph_state.next)
                interrupt_node = graph_state.next[0] if graph_state.next else None

        # Flush Langfuse events
        if langfuse_callback:
            self._tracer.flush()

        logger.info(
            "workflow_finished",
            task_id=str(task_id),
            status=final_state.get("task_status"),
            error=final_state.get("error"),
            trace_url=trace_url,
            interrupted=interrupted,
            interrupt_node=interrupt_node,
        )

        final_state["trace_url"] = trace_url
        return WorkflowResult(
            state=final_state,
            interrupted=interrupted,
            interrupt_node=interrupt_node,
        )

    async def resume(
        self,
        task_id: str | UUID,
        user_input: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """Resume a paused workflow from checkpoint.

        This allows continuing execution after an interrupt or pause.

        Args:
            task_id: Task UUID (string or UUID)
            user_input: Optional dict with user input data to provide at the interrupt point

        Returns:
            WorkflowResult containing state and interrupt status
        """
        if isinstance(task_id, str):
            task_id = UUID(task_id)

        thread_id = str(task_id)

        async with lifespan(self.session) as container:
            async with get_checkpointer() as checkpointer:
                compiled = compile_workflow(self.session, checkpointer=checkpointer)

                # Resume from checkpoint with optional user input
                resume_input = user_input

                config: RunnableConfig = {
                    "recursion_limit": 100,
                    "configurable": {
                        "thread_id": thread_id,
                        "ws_manager": self.ws_manager,
                        "container": container,
                        "event_bus": self.event_bus,
                        "breakpoint_service": self.breakpoint_service,
                    },
                }

                final_state: AgentState = cast(
                    AgentState,
                    await compiled.ainvoke(resume_input, config=config),
                )

                # Check if workflow was interrupted again (another breakpoint)
                graph_state = await compiled.aget_state(config)
                interrupted = bool(graph_state.next)
                interrupt_node = graph_state.next[0] if graph_state.next else None

        logger.info(
            "workflow_resumed",
            task_id=str(task_id),
            status=final_state.get("task_status"),
            interrupted=interrupted,
            interrupt_node=interrupt_node,
        )

        return WorkflowResult(
            state=final_state,
            interrupted=interrupted,
            interrupt_node=interrupt_node,
        )

    async def get_state(
        self,
        task_id: str | UUID,
    ) -> AgentState | None:
        """Get the current state of a workflow from checkpoint.

        Args:
            task_id: Task UUID

        Returns:
            Current workflow state or None if no checkpoint exists
        """
        if isinstance(task_id, str):
            task_id = UUID(task_id)

        thread_id = str(task_id)

        async with get_checkpointer() as checkpointer:
            compiled = compile_workflow(self.session, checkpointer=checkpointer)

            state = await compiled.aget_state(
                config=cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
            )

            if state.values:
                return cast(AgentState, state.values)
        return None
