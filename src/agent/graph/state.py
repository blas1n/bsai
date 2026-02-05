"""LangGraph workflow state definition.

Immutable state structure for multi-agent orchestration.
All updates should return new dicts, not mutate existing state.

Simplified 7-node workflow:
    architect -> plan_review -> execute_worker -> verify_qa
        -> execution_breakpoint -> advance -> generate_response -> END
"""

from typing import TYPE_CHECKING, Any, NotRequired, TypedDict
from uuid import UUID

from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.db.models.project_plan import ProjectPlan
from agent.llm import ChatMessage
from agent.llm.schemas import PlanStatus

if TYPE_CHECKING:
    from agent.services.dependency_graph import DependencyGraph
    from agent.services.execution_engine import ExecutionStatus


class MilestoneData(TypedDict):
    """Milestone data structure within state.

    Represents a single milestone's complete state during workflow execution.
    """

    id: UUID
    description: str
    complexity: TaskComplexity
    acceptance_criteria: str
    status: MilestoneStatus
    selected_model: str | None
    generated_prompt: str | None
    worker_output: str | None
    qa_feedback: str | None
    retry_count: int


class AgentState(TypedDict):
    """Immutable state for LangGraph workflow.

    All updates should return new dicts, not mutate existing state.
    Required fields are always present, NotRequired fields may be omitted
    in partial updates from node functions.

    State Categories:
    1. Session Context - Identifies the workflow execution (Required)
    2. Task Status - Overall task progress
    3. Milestones - List of work items with individual progress
    4. Current Processing - Active milestone state
    5. Context Management - Memory and token tracking
    6. Error Tracking - Failure information
    7. Workflow Control - Execution flow flags
    8. Project Plan - Architect output and HITL review
    9. Parallel Execution - Dependency graph and execution status
    """

    # Session context (Required)
    session_id: UUID
    task_id: UUID
    user_id: str
    original_request: str

    # Task status
    task_status: NotRequired[TaskStatus]

    # Milestones (list of MilestoneData)
    milestones: NotRequired[list[MilestoneData]]
    current_milestone_index: NotRequired[int]

    # Current milestone processing state
    current_prompt: NotRequired[str | None]
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

    # Long-term memory (retrieved from past experiences)
    relevant_memories: NotRequired[list[dict[str, Any]]]  # Retrieved memories
    memory_context: NotRequired[str | None]  # Formatted memory context for LLM

    # Project Plan (Architect agent output)
    project_plan: NotRequired[ProjectPlan | None]  # Hierarchical project plan
    plan_status: NotRequired[PlanStatus | None]  # Current plan status

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
        "DependencyGraph | None"
    ]  # Task dependency graph for parallel execution
    ready_tasks: NotRequired[list[str]]  # List of task IDs ready for parallel execution
    execution_status: NotRequired["ExecutionStatus | None"]  # Current execution engine status
    current_task_id: NotRequired[str | None]  # Current task ID being executed (project_plan flow)


def update_milestone(milestone: MilestoneData, **updates: Any) -> MilestoneData:
    """Create an updated copy of a milestone with the given changes.

    Args:
        milestone: Original milestone data
        **updates: Fields to update

    Returns:
        New MilestoneData with updates applied
    """
    merged: dict[str, Any] = {**milestone, **updates}
    result: MilestoneData = MilestoneData(
        id=merged["id"],
        description=merged["description"],
        complexity=merged["complexity"],
        acceptance_criteria=merged["acceptance_criteria"],
        status=merged["status"],
        selected_model=merged["selected_model"],
        generated_prompt=merged["generated_prompt"],
        worker_output=merged["worker_output"],
        qa_feedback=merged["qa_feedback"],
        retry_count=merged["retry_count"],
    )
    return result
