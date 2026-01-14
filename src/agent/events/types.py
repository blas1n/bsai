"""Event type definitions for the event bus.

All events inherit from Event base class and include explicit status fields
to eliminate frontend heuristics.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from agent.api.schemas.websocket import PreviousMilestoneInfo
from agent.db.models.enums import MilestoneStatus

__all__ = [
    "EventType",
    "AgentStatus",
    "Event",
    "TaskStartedEvent",
    "TaskProgressEvent",
    "TaskCompletedEvent",
    "TaskFailedEvent",
    "MilestoneStatusChangedEvent",
    "MilestoneRetryEvent",
    "AgentActivityEvent",
    "LLMChunkEvent",
    "LLMCompleteEvent",
    "ContextCompressedEvent",
    "BreakpointHitEvent",
    "BreakpointResumedEvent",
    "MilestoneStatus",
]


class EventType(StrEnum):
    """All event types in the system."""

    # Task lifecycle
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    # Milestone lifecycle
    MILESTONE_CREATED = "milestone.created"
    MILESTONE_STARTED = "milestone.started"
    MILESTONE_STATUS_CHANGED = "milestone.status_changed"
    MILESTONE_COMPLETED = "milestone.completed"
    MILESTONE_FAILED = "milestone.failed"
    MILESTONE_RETRY = "milestone.retry"

    # Agent activity
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    # LLM streaming
    LLM_CHUNK = "llm.chunk"
    LLM_COMPLETE = "llm.complete"

    # Context management
    CONTEXT_COMPRESSED = "context.compressed"

    # Breakpoint (Human-in-the-Loop)
    BREAKPOINT_HIT = "breakpoint.hit"
    BREAKPOINT_RESUMED = "breakpoint.resumed"
    BREAKPOINT_REJECTED = "breakpoint.rejected"


class AgentStatus(StrEnum):
    """Explicit agent activity status."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class Event(BaseModel):
    """Base class for all events.

    All events must include session_id, task_id, and timestamp.
    """

    type: EventType
    session_id: UUID
    task_id: UUID
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"use_enum_values": True}


# =============================================================================
# Task Events
# =============================================================================


class TaskStartedEvent(Event):
    """Emitted when a task starts execution."""

    type: EventType = EventType.TASK_STARTED
    original_request: str
    milestone_count: int = 0
    previous_milestones: list[PreviousMilestoneInfo] = Field(default_factory=list)
    trace_url: str = ""


class TaskProgressEvent(Event):
    """Emitted when task progress updates (milestone advancement)."""

    type: EventType = EventType.TASK_PROGRESS
    current_milestone: int  # 1-based index
    total_milestones: int
    progress: float  # 0.0 to 1.0
    current_milestone_title: str


class TaskCompletedEvent(Event):
    """Emitted when a task completes successfully."""

    type: EventType = EventType.TASK_COMPLETED
    final_result: str
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: Decimal
    duration_seconds: float
    trace_url: str = ""


class TaskFailedEvent(Event):
    """Emitted when a task fails."""

    type: EventType = EventType.TASK_FAILED
    error: str
    failed_milestone: int | None = None  # sequence_number if applicable


# =============================================================================
# Milestone Events
# =============================================================================


class MilestoneStatusChangedEvent(Event):
    """Emitted when milestone status changes.

    Includes explicit previous and new status for clear state transitions.
    """

    type: EventType = EventType.MILESTONE_STATUS_CHANGED
    milestone_id: UUID
    sequence_number: int
    previous_status: MilestoneStatus
    new_status: MilestoneStatus
    agent: str  # Agent that triggered the change
    message: str
    details: dict[str, Any] | None = None


class MilestoneRetryEvent(Event):
    """Emitted when a milestone is retried after QA failure."""

    type: EventType = EventType.MILESTONE_RETRY
    milestone_id: UUID
    sequence_number: int
    retry_count: int
    max_retries: int = 3
    feedback: str | None = None


# =============================================================================
# Agent Activity Events
# =============================================================================


class AgentActivityEvent(Event):
    """Emitted when an agent starts or completes work.

    The status field is EXPLICIT - no heuristics needed on frontend.
    """

    type: EventType = EventType.AGENT_STARTED  # or AGENT_COMPLETED
    milestone_id: UUID
    sequence_number: int
    agent: str  # conductor, meta_prompter, worker, qa, summarizer, responder
    status: AgentStatus  # started, completed, failed
    message: str
    details: dict[str, Any] | None = None


# =============================================================================
# LLM Streaming Events
# =============================================================================


class LLMChunkEvent(Event):
    """Emitted for each LLM streaming chunk."""

    type: EventType = EventType.LLM_CHUNK
    milestone_id: UUID
    chunk: str
    chunk_index: int
    agent: str


class LLMCompleteEvent(Event):
    """Emitted when LLM streaming completes."""

    type: EventType = EventType.LLM_COMPLETE
    milestone_id: UUID
    full_content: str
    tokens_used: int
    agent: str


# =============================================================================
# Context Events
# =============================================================================


class ContextCompressedEvent(Event):
    """Emitted when context is compressed to free memory."""

    type: EventType = EventType.CONTEXT_COMPRESSED
    old_message_count: int
    new_message_count: int
    tokens_saved_estimate: int


# =============================================================================
# Breakpoint Events
# =============================================================================


class BreakpointHitEvent(Event):
    """Emitted when workflow hits a breakpoint."""

    type: EventType = EventType.BREAKPOINT_HIT
    node_name: str
    agent_type: str
    current_milestone_index: int
    total_milestones: int
    milestones: list[dict[str, Any]]
    last_worker_output: str | None = None
    last_qa_result: dict[str, Any] | None = None


class BreakpointResumedEvent(Event):
    """Emitted when workflow resumes from breakpoint."""

    type: EventType = EventType.BREAKPOINT_RESUMED
    node_name: str
    user_input: str | None = None
