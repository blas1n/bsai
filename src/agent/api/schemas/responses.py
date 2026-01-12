"""Response schemas for API endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agent.db.models.enums import (
    MilestoneStatus,
    SessionStatus,
    SnapshotType,
    TaskComplexity,
    TaskStatus,
)

T = TypeVar("T")


class SessionResponse(BaseModel):
    """Response schema for session data."""

    id: UUID
    user_id: str | None = None
    status: SessionStatus
    title: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: Decimal = Decimal("0")
    context_usage_ratio: float = 0.0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskResponse(BaseModel):
    """Response schema for task data."""

    id: UUID
    session_id: UUID
    original_request: str
    status: TaskStatus
    final_result: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentStepResponse(BaseModel):
    """Response schema for agent execution step."""

    id: UUID
    task_id: UUID
    milestone_id: UUID | None = None
    agent_type: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MilestoneResponse(BaseModel):
    """Response schema for milestone data."""

    id: UUID
    task_id: UUID
    sequence_number: int
    title: str
    description: str = ""
    complexity: TaskComplexity
    status: MilestoneStatus
    selected_llm: str | None = None
    retry_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True, ser_json_bytes="base64", ser_json_timedelta="float"
    )


class MilestoneDetailResponse(MilestoneResponse):
    """Detailed milestone response with output content."""

    worker_output: str | None = None
    qa_result: str | None = None
    acceptance_criteria: str | None = None


class TaskDetailResponse(TaskResponse):
    """Detailed task response with milestones and agent steps."""

    milestones: list[MilestoneResponse] = []
    agent_steps: list[AgentStepResponse] = []
    progress: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Task completion progress (0.0 - 1.0)",
    )
    total_duration_ms: int | None = Field(
        default=None,
        description="Total execution duration in milliseconds",
    )
    cost_breakdown: dict[str, Any] = Field(
        default_factory=dict,
        description="Cost breakdown by agent type",
    )


class SessionDetailResponse(SessionResponse):
    """Detailed session response with tasks."""

    tasks: list[TaskResponse] = []
    active_task: TaskResponse | None = None


class SnapshotResponse(BaseModel):
    """Response schema for memory snapshot data."""

    id: UUID
    session_id: UUID
    snapshot_type: SnapshotType
    compressed_context: str
    key_decisions: dict[str, Any] | None = None
    token_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int = Field(description="Total number of items")
    limit: int = Field(description="Items per page")
    offset: int = Field(description="Number of items skipped")
    has_more: bool = Field(description="Whether more items exist")


class ArtifactResponse(BaseModel):
    """Response schema for artifact data."""

    id: UUID
    task_id: UUID
    milestone_id: UUID | None = None
    artifact_type: str = Field(description="Type of artifact (code, file, document)")
    filename: str
    language: str | None = None
    content: str
    path: str | None = Field(default=None, description="Path within project structure")
    sequence_number: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Standardized error response."""

    error: str = Field(description="Error message")
    detail: str | None = Field(default=None, description="Detailed error information")
    code: str = Field(description="Error code (e.g., HTTP_404)")
    request_id: str = Field(description="Request ID for tracking")
