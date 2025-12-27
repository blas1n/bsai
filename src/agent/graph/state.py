"""LangGraph workflow state definition.

Immutable state structure for multi-agent orchestration.
All updates should return new dicts, not mutate existing state.
"""

from typing import TypedDict
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


class AgentState(TypedDict, total=False):
    """Immutable state for LangGraph workflow.

    All updates should return new dicts, not mutate existing state.
    Using total=False allows partial updates from node functions.

    State Categories:
    1. Session Context - Identifies the workflow execution
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
    task_status: TaskStatus

    # Milestones (list of MilestoneData)
    milestones: list[MilestoneData]
    current_milestone_index: int

    # Current milestone processing state
    current_prompt: str | None
    current_output: str | None
    current_qa_decision: str | None  # "pass", "retry", "fail"
    current_qa_feedback: str | None
    retry_count: int

    # Context management
    context_messages: list[ChatMessage]
    context_summary: str | None
    current_context_tokens: int
    max_context_tokens: int

    # Memory state
    needs_compression: bool

    # Error tracking
    error: str | None
    error_node: str | None

    # Workflow control
    should_continue: bool
    workflow_complete: bool
