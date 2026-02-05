"""LangGraph workflow state definition.

Immutable state structure for multi-agent orchestration.
All updates should return new dicts, not mutate existing state.

Simplified 7-node workflow:
    architect -> plan_review -> execute_worker -> verify_qa
        -> execution_breakpoint -> advance -> generate_response -> END

Field Groups:
    1. Session Context - Required identifiers for workflow execution
    2. Project Plan - Architect output with hierarchical task structure
    3. Task Processing - Current task execution state and QA results
    4. Context Management - Conversation history and token tracking
    5. Workflow Control - Execution flow flags and error state
    6. Human-in-the-Loop - Plan review and breakpoint configuration
"""

from typing import NotRequired, TypedDict
from uuid import UUID

from agent.db.models.enums import TaskStatus
from agent.db.models.project_plan import ProjectPlan
from agent.llm import ChatMessage
from agent.llm.schemas import PlanStatus


class AgentState(TypedDict):
    """Immutable state for LangGraph workflow.

    All updates should return new dicts, not mutate existing state.
    Required fields are always present, NotRequired fields may be omitted
    in partial updates from node functions.
    """

    # =========================================================================
    # 1. SESSION CONTEXT (Required)
    # =========================================================================
    session_id: UUID
    task_id: UUID
    user_id: str
    original_request: str

    # =========================================================================
    # 2. PROJECT PLAN (Architect agent output)
    # =========================================================================
    project_plan: NotRequired[ProjectPlan | None]
    """Hierarchical project plan created by Architect agent."""

    plan_status: NotRequired[PlanStatus | None]
    """Current plan status (DRAFT, APPROVED, REJECTED)."""

    current_task_id: NotRequired[str | None]
    """Current task ID being executed (e.g., "T1.1.1")."""

    current_milestone_index: NotRequired[int]
    """Index of current task in the flattened task list."""

    # =========================================================================
    # 3. TASK PROCESSING (Worker and QA state)
    # =========================================================================
    task_status: NotRequired[TaskStatus]
    """Overall task status (PENDING, IN_PROGRESS, COMPLETED, FAILED)."""

    current_output: NotRequired[str | None]
    """Latest output from Worker agent."""

    current_prompt: NotRequired[str | None]
    """Current prompt being processed."""

    current_qa_decision: NotRequired[str | None]
    """QA decision: "pass", "retry", or "fail"."""

    current_qa_feedback: NotRequired[str | None]
    """Structured feedback from QA agent for retry."""

    retry_count: NotRequired[int]
    """Number of retry attempts for current task (max 3)."""

    # =========================================================================
    # 4. CONTEXT MANAGEMENT (Memory and tokens)
    # =========================================================================
    context_messages: NotRequired[list[ChatMessage]]
    """Conversation history for context."""

    context_summary: NotRequired[str | None]
    """Compressed summary of prior context."""

    current_context_tokens: NotRequired[int]
    """Current token count of context."""

    max_context_tokens: NotRequired[int]
    """Maximum allowed context tokens."""

    total_input_tokens: NotRequired[int]
    """Cumulative input tokens used."""

    total_output_tokens: NotRequired[int]
    """Cumulative output tokens used."""

    total_cost_usd: NotRequired[str]
    """Total cost in USD (string for JSON serialization)."""

    # =========================================================================
    # 5. WORKFLOW CONTROL (Execution flow and errors)
    # =========================================================================
    should_continue: NotRequired[bool]
    """Whether to continue to next task."""

    workflow_complete: NotRequired[bool]
    """Whether all tasks are done or workflow errored."""

    error: NotRequired[str | None]
    """Error message if workflow failed."""

    error_node: NotRequired[str | None]
    """Node name where error occurred."""

    final_response: NotRequired[str | None]
    """Final user-facing response from Responder agent."""

    trace_url: NotRequired[str]
    """Langfuse trace URL for observability."""

    # =========================================================================
    # 6. HUMAN-IN-THE-LOOP (Plan review and breakpoints)
    # =========================================================================
    # Plan Review
    waiting_for_plan_review: NotRequired[bool]
    """Whether waiting for user to review plan."""

    revision_requested: NotRequired[bool]
    """Whether user requested plan revision."""

    revision_feedback: NotRequired[str | None]
    """User's feedback for plan revision."""

    # Breakpoint Configuration
    breakpoint_enabled: NotRequired[bool]
    """Whether breakpoints are enabled for this task."""

    breakpoint_nodes: NotRequired[list[str]]
    """List of node names where execution should pause."""

    breakpoint_user_input: NotRequired[str | None]
    """User input provided at a breakpoint."""
