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
from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.db.repository.artifact_repo import ArtifactRepository
from agent.db.repository.memory_snapshot_repo import MemorySnapshotRepository
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.llm import ChatMessage

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
from .state import AgentState, MilestoneData

if TYPE_CHECKING:
    from langgraph.graph.graph import CompiledGraph
    from sqlalchemy.ext.asyncio import AsyncSession

    from agent.api.websocket.manager import ConnectionManager
    from agent.cache import SessionCache

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
        cache: SessionCache | None = None,
    ) -> None:
        """Initialize workflow runner.

        Args:
            session: Database session for the workflow
            ws_manager: Optional WebSocket manager for real-time updates
            cache: Optional session cache for context persistence
        """
        self.session = session
        self.ws_manager = ws_manager
        self.cache = cache

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

        Also includes recent artifacts from the session for better context.

        Args:
            session_id: Session UUID

        Returns:
            Tuple of (context_messages, context_summary, estimated_tokens)
        """
        context_messages: list[ChatMessage] = []
        context_summary: str | None = None
        token_count = 0

        # Try cache first
        if self.cache:
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

        # Add recent artifacts as additional context
        artifact_repo = ArtifactRepository(self.session)
        recent_artifacts = await artifact_repo.get_by_session_id(session_id, limit=10)
        if recent_artifacts:
            artifact_summaries = []
            for artifact in reversed(recent_artifacts):  # Oldest first
                summary = f"- {artifact.filename} ({artifact.kind})"
                if len(artifact.content) <= 500:
                    summary += f":\n```{artifact.kind}\n{artifact.content}\n```"
                else:
                    # Truncate long content
                    summary += f" [{len(artifact.content)} chars, truncated]:\n```{artifact.kind}\n{artifact.content[:300]}...\n```"
                artifact_summaries.append(summary)

            artifacts_context = "Previously created artifacts in this session:\n" + "\n".join(
                artifact_summaries
            )
            context_messages.append(ChatMessage(role="system", content=artifacts_context))
            # Update token estimate
            token_count += len(artifacts_context) // 4
            logger.info(
                "artifacts_added_to_context",
                session_id=str(session_id),
                artifact_count=len(recent_artifacts),
            )

        return context_messages, context_summary, token_count

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

        # Load previous context and milestones from same session
        context_messages, context_summary, context_tokens = await self._load_previous_context(
            session_id
        )
        previous_milestones, max_sequence = await self._load_previous_milestones(session_id)

        # Build initial state with previous context and milestones
        initial_state: AgentState = {
            "session_id": session_id,
            "task_id": task_id,
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
        }

        logger.info(
            "workflow_started",
            session_id=str(session_id),
            task_id=str(task_id),
            has_previous_context=len(context_messages) > 0,
            previous_milestone_count=len(previous_milestones),
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
