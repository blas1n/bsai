"""LangGraph workflow state definition.

Immutable state structure for multi-agent orchestration.
All updates should return new dicts, not mutate existing state.

Simplified 7-node workflow:
    architect -> plan_review -> execute_worker -> verify_qa
        -> execution_breakpoint -> advance -> generate_response -> END
"""

from typing import NotRequired, TypedDict
from uuid import UUID

from agent.db.models.enums import TaskStatus
from agent.db.models.project_plan import ProjectPlan
from agent.llm import ChatMessage
from agent.llm.schemas import PlanStatus
from agent.services.dependency_graph import DependencyGraph


class AgentState(TypedDict):
    """Immutable state for LangGraph workflow.

    All updates should return new dicts, not mutate existing state.
    Required fields are always present, NotRequired fields may be omitted
    in partial updates from node functions.

    State Categories:
    1. Session Context - Identifies the workflow execution (Required)
    2. Task Status - Overall task progress
    3. Project Plan - Architect output with hierarchical tasks
    4. Current Processing - Active task state
    5. Context Management - Memory and token tracking
    6. Error Tracking - Failure information
    7. Workflow Control - Execution flow flags
    8. Human-in-the-Loop - Plan review and breakpoints
    9. Parallel Execution - Dependency graph for task ordering
    """

    # Session context (Required)
    session_id: UUID
    task_id: UUID
    user_id: str
    original_request: str

    # Task status
    task_status: NotRequired[TaskStatus]

    # Project Plan (Architect agent output)
    project_plan: NotRequired[ProjectPlan | None]  # Hierarchical project plan
    plan_status: NotRequired[PlanStatus | None]  # Current plan status
    current_task_id: NotRequired[str | None]  # Current task ID being executed (e.g., "T1.1.1")

    # Current task processing state
    current_output: NotRequired[str | None]
    current_qa_decision: NotRequired[str | None]  # "pass", "retry", "fail"
    current_qa_feedback: NotRequired[str | None]
    retry_count: NotRequired[int]

    # Context management
    context_messages: NotRequired[list[ChatMessage]]
    context_summary: NotRequired[str | None]
    current_context_tokens: NotRequired[int]
    max_context_tokens: NotRequired[int]

    # Token and cost tracking
    total_input_tokens: NotRequired[int]
    total_output_tokens: NotRequired[int]
    total_cost_usd: NotRequired[str]  # Stored as string for JSON serialization

    # Error tracking
    error: NotRequired[str | None]
    error_node: NotRequired[str | None]

    # Workflow control
    should_continue: NotRequired[bool]
    workflow_complete: NotRequired[bool]

    # Final response (from Responder agent)
    final_response: NotRequired[str | None]

    # Observability
    trace_url: NotRequired[str]  # Langfuse trace URL (empty string if disabled)

    # Plan Review (Human-in-the-Loop for Architect)
    waiting_for_plan_review: NotRequired[bool]  # Whether waiting for user review
    revision_requested: NotRequired[bool]  # Whether user requested revision
    revision_feedback: NotRequired[str | None]  # User's revision feedback

    # Breakpoint configuration (Human-in-the-Loop)
    breakpoint_enabled: NotRequired[bool]  # Whether breakpoints are enabled
    breakpoint_nodes: NotRequired[list[str]]  # List of node names to pause at
    breakpoint_user_input: NotRequired[str | None]  # User input at breakpoint

    # Parallel execution fields
    dependency_graph: NotRequired[
        DependencyGraph | None
    ]  # Task dependency graph for parallel execution
    ready_tasks: NotRequired[list[str]]  # List of task IDs ready for parallel execution
