"""LangGraph workflow state definition.

Immutable state structure for multi-agent orchestration.
All updates should return new dicts, not mutate existing state.
"""

from typing import TYPE_CHECKING, Any, NotRequired, TypedDict
from uuid import UUID

from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.llm import ChatMessage
from agent.llm.schemas import PlanStatus

if TYPE_CHECKING:
    from agent.db.models.project_plan import ProjectPlan


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

    # ReAct replanning metadata (optional)
    is_modified: NotRequired[bool]  # True if added/modified during replan
    added_at_replan: NotRequired[int | None]  # Replan iteration when added (None = original)


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
    """

    # Session context
    session_id: UUID
    task_id: UUID
    user_id: str
    original_request: str

    # Task status
    task_status: NotRequired[TaskStatus]

    # Milestones (list of MilestoneData)
    milestones: NotRequired[list[MilestoneData]]
    current_milestone_index: NotRequired[int]
    milestone_sequence_offset: NotRequired[int]  # Offset for new milestone numbering

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

    # Memory state
    needs_compression: NotRequired[bool]

    # Error tracking
    error: NotRequired[str | None]
    error_node: NotRequired[str | None]

    # Workflow control
    should_continue: NotRequired[bool]
    workflow_complete: NotRequired[bool]

    # Task summary (from Task Summary agent)
    task_summary: NotRequired[dict[str, Any]]

    # Final response (from Responder agent)
    final_response: NotRequired[str | None]

    # Observability
    trace_url: NotRequired[str]  # Langfuse trace URL (empty string if disabled)

    # Breakpoint configuration (Human-in-the-Loop)
    breakpoint_enabled: NotRequired[bool]  # Whether breakpoints are enabled
    breakpoint_nodes: NotRequired[list[str]]  # List of node names to pause at
    breakpoint_user_input: NotRequired[str | None]  # User input at breakpoint

    # Long-term memory (retrieved from past experiences)
    relevant_memories: NotRequired[list[dict[str, Any]]]  # Retrieved memories
    memory_context: NotRequired[str | None]  # Formatted memory context for LLM

    # ReAct dynamic planning fields
    plan_modifications: NotRequired[list[dict[str, Any]]]  # History of plan changes
    replan_count: NotRequired[int]  # Number of replan iterations (max 3)
    plan_confidence: NotRequired[float]  # 0.0-1.0 confidence in current plan
    current_observations: NotRequired[list[str]]  # Observations from Worker
    needs_replan: NotRequired[bool]  # Flag set by QA when replan needed
    replan_reason: NotRequired[str | None]  # Why replan was triggered

    # Project Plan (Architect agent output)
    project_plan: NotRequired[ProjectPlan | None]  # Hierarchical project plan
    plan_status: NotRequired[PlanStatus | None]  # Current plan status

    # Failure recovery fields
    strategy_retry_attempted: NotRequired[bool]  # Whether strategy retry has been attempted
    failure_context: NotRequired[dict[str, Any]]  # Context for failure report generation


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
    # Add optional ReAct fields if present
    if "is_modified" in merged:
        result["is_modified"] = merged["is_modified"]
    if "added_at_replan" in merged:
        result["added_at_replan"] = merged["added_at_replan"]
    return result
