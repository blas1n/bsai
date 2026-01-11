"""WebSocket message schemas and types."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from agent.db.models.enums import MilestoneStatus


class WSMessageType(StrEnum):
    """WebSocket message types."""

    # Client -> Server
    AUTH = "auth"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"

    # Server -> Client (Auth)
    AUTH_SUCCESS = "auth_success"
    AUTH_ERROR = "auth_error"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    PONG = "pong"

    # Task Events
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    # Milestone Events
    MILESTONE_STARTED = "milestone_started"
    MILESTONE_PROGRESS = "milestone_progress"
    MILESTONE_COMPLETED = "milestone_completed"
    MILESTONE_FAILED = "milestone_failed"
    MILESTONE_RETRY = "milestone_retry"

    # LLM Streaming
    LLM_CHUNK = "llm_chunk"
    LLM_COMPLETE = "llm_complete"

    # Session Events
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    CONTEXT_COMPRESSED = "context_compressed"

    # Errors
    ERROR = "error"

    # MCP Tool Execution
    MCP_TOOL_CALL_REQUEST = "mcp_tool_call_request"
    MCP_TOOL_CALL_RESPONSE = "mcp_tool_call_response"
    MCP_APPROVAL_REQUEST = "mcp_approval_request"
    MCP_APPROVAL_RESPONSE = "mcp_approval_response"


class WSMessage(BaseModel):
    """WebSocket message envelope."""

    type: WSMessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: str | None = None


# Task Event Payloads


class PreviousMilestoneInfo(BaseModel):
    """Previous milestone info for session continuity."""

    id: UUID
    sequence_number: int
    description: str
    complexity: str
    status: str
    worker_output: str | None = None


class TaskStartedPayload(BaseModel):
    """Payload for TASK_STARTED event."""

    task_id: UUID
    session_id: UUID
    original_request: str
    milestone_count: int = 0
    previous_milestones: list[PreviousMilestoneInfo] = Field(default_factory=list)
    trace_url: str = Field(
        default="",
        description="Langfuse trace URL for debugging and observability",
    )


class TaskProgressPayload(BaseModel):
    """Payload for TASK_PROGRESS event."""

    task_id: UUID
    current_milestone: int
    total_milestones: int
    progress: float = Field(ge=0.0, le=1.0)
    current_milestone_title: str


class TaskCompletedPayload(BaseModel):
    """Payload for TASK_COMPLETED event."""

    task_id: UUID
    final_result: str
    total_tokens: int
    total_cost_usd: Decimal
    duration_seconds: float
    trace_url: str = Field(
        default="",
        description="Langfuse trace URL for debugging and observability",
    )


class TaskFailedPayload(BaseModel):
    """Payload for TASK_FAILED event."""

    task_id: UUID
    error: str
    failed_milestone: int | None = None


class MilestoneProgressPayload(BaseModel):
    """Payload for milestone progress events."""

    milestone_id: UUID
    task_id: UUID
    sequence_number: int
    status: MilestoneStatus
    agent: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)  # Additional agent-specific details


class LLMChunkPayload(BaseModel):
    """Payload for LLM_CHUNK event (streaming)."""

    task_id: UUID
    milestone_id: UUID
    chunk: str
    chunk_index: int
    agent: str = Field(description="Agent name: worker, qa, meta_prompter")


class LLMCompletePayload(BaseModel):
    """Payload for LLM_COMPLETE event."""

    task_id: UUID
    milestone_id: UUID
    full_content: str
    tokens_used: int
    agent: str
