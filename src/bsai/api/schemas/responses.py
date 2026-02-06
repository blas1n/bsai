"""Response schemas for API endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from bsai.db.models.enums import (
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
    """Detailed task response with project plan and agent steps."""

    project_plan: dict[str, Any] | None = Field(
        default=None,
        description="Project plan with hierarchical tasks",
    )
    milestones: list[MilestoneResponse] = Field(
        default_factory=list,
        description="Task milestones",
    )
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
    session_id: UUID
    task_id: UUID | None = None
    milestone_id: UUID | None = None
    artifact_type: str = Field(description="Type of artifact (code, file, document)")
    filename: str
    language: str | None = None
    content: str
    path: str | None = Field(default=None, description="Path within project structure")
    sequence_number: int = 0
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Standardized error response."""

    error: str = Field(description="Error message")
    detail: str | None = Field(default=None, description="Detailed error information")
    code: str = Field(description="Error code (e.g., HTTP_404)")
    request_id: str = Field(description="Request ID for tracking")


class FeatureProgress(BaseModel):
    """Progress information for a feature."""

    id: str = Field(description="Feature ID")
    title: str = Field(description="Feature title")
    completed: int = Field(description="Number of completed tasks")
    total: int = Field(description="Total number of tasks")
    percent: float = Field(description="Completion percentage (0-100)")


class EpicProgress(BaseModel):
    """Progress information for an epic."""

    id: str = Field(description="Epic ID")
    title: str = Field(description="Epic title")
    completed: int = Field(description="Number of completed tasks")
    total: int = Field(description="Total number of tasks")
    percent: float = Field(description="Completion percentage (0-100)")


class ProgressResponse(BaseModel):
    """Task progress response.

    Returns progress information including:
    - Overall completion percentage
    - Task/Feature/Epic level progress
    - Current breakpoint reason (if paused)
    """

    total_tasks: int = Field(description="Total number of tasks")
    completed_tasks: int = Field(description="Number of completed tasks")
    pending_tasks: int = Field(description="Number of pending tasks")
    failed_tasks: int = Field(description="Number of failed tasks")
    overall_percent: float = Field(description="Overall completion percentage (0-100)")
    current_task: str | None = Field(
        default=None,
        description="Current task ID (if in progress)",
    )
    breakpoint_reason: str | None = Field(
        default=None,
        description="Reason for breakpoint pause (if paused)",
    )
    feature_progress: list[FeatureProgress] = Field(
        default_factory=list,
        description="Progress for each feature",
    )
    epic_progress: list[EpicProgress] = Field(
        default_factory=list,
        description="Progress for each epic",
    )


class ActionResponse(BaseModel):
    """Generic action response."""

    success: bool = Field(description="Whether the action was successful")
    message: str = Field(description="Action result message")


# =============================================================================
# QA Result Response Models
# =============================================================================


class LintResultResponse(BaseModel):
    """Lint result for API."""

    success: bool = Field(description="Whether linting passed")
    errors: int = Field(description="Number of lint errors")
    warnings: int = Field(description="Number of lint warnings")
    issues: list[str] = Field(default_factory=list, description="List of lint issues")


class TypecheckResultResponse(BaseModel):
    """Typecheck result for API."""

    success: bool = Field(description="Whether type checking passed")
    errors: int = Field(description="Number of type errors")
    issues: list[str] = Field(default_factory=list, description="List of type check issues")


class TestResultResponse(BaseModel):
    """Test result for API."""

    success: bool = Field(description="Whether all tests passed")
    passed: int = Field(description="Number of passed tests")
    failed: int = Field(description="Number of failed tests")
    skipped: int = Field(description="Number of skipped tests")
    total: int = Field(description="Total number of tests")
    coverage: float | None = Field(default=None, description="Test coverage percentage")
    failed_tests: list[str] = Field(default_factory=list, description="List of failed test names")


class BuildResultResponse(BaseModel):
    """Build result for API."""

    success: bool = Field(description="Whether build succeeded")
    error_message: str | None = Field(default=None, description="Build error message if failed")


class QAResultResponse(BaseModel):
    """API response for QA results."""

    task_id: UUID = Field(description="Task UUID")
    decision: str = Field(description="QA decision (PASS or RETRY)")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    summary: str = Field(description="Summary of QA validation")

    # Detailed results
    static_analysis: dict[str, Any] | None = Field(
        default=None, description="Static analysis results (issues and suggestions)"
    )
    lint: LintResultResponse | None = Field(default=None, description="Lint validation result")
    typecheck: TypecheckResultResponse | None = Field(
        default=None, description="Type check validation result"
    )
    test: TestResultResponse | None = Field(default=None, description="Test execution result")
    build: BuildResultResponse | None = Field(default=None, description="Build verification result")
