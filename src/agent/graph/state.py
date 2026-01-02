"""LangGraph workflow state definition.

Immutable state structure for multi-agent orchestration.
All updates should return new dicts, not mutate existing state.
"""

from typing import NotRequired, TypedDict
from uuid import UUID

from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.llm import ChatMessage


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
    """

    # Session context
    session_id: UUID
    task_id: UUID
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

    # Final response (from Responder agent)
    final_response: NotRequired[str | None]
