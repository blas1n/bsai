"""Request schemas for API endpoints."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from bsai.llm.schemas import BreakpointConfig, QAConfig


class SessionCreate(BaseModel):
    """Request schema for creating a new session."""

    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional session metadata",
    )


class BulkSessionAction(BaseModel):
    """Request schema for bulk session operations."""

    session_ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of session IDs to operate on",
    )
    action: Literal["pause", "complete", "delete"] = Field(
        ...,
        description="Action to perform on the sessions",
    )


class TaskCreate(BaseModel):
    """Request schema for creating a new task."""

    original_request: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="User's original request/task description",
    )
    max_context_tokens: int = Field(
        default=100000,
        ge=1000,
        le=200000,
        description="Maximum context window size in tokens",
    )
    stream: bool = Field(
        default=True,
        description="Enable WebSocket streaming for task execution",
    )
    breakpoint_enabled: bool = Field(
        default=False,
        description="Enable breakpoints for human-in-the-loop workflow",
    )
    breakpoint_nodes: list[str] = Field(
        default_factory=lambda: ["plan_review"],
        description="List of node names to pause at: plan_review, execution_breakpoint. Use 'all' for all.",
    )
    breakpoint_config: BreakpointConfig | None = Field(
        default=None,
        description="Breakpoint configuration for execution control",
    )
    qa_config: QAConfig | None = Field(
        default=None,
        description="QA configuration for validation settings",
    )


class SnapshotCreate(BaseModel):
    """Request schema for creating a manual snapshot."""

    reason: str = Field(
        default="Manual checkpoint",
        max_length=500,
        description="Reason for creating the snapshot",
    )


class TaskResume(BaseModel):
    """Request schema for resuming a paused task from a breakpoint."""

    user_input: str | None = Field(
        default=None,
        max_length=10000,
        description="Optional user input/feedback to pass to the workflow",
    )
    rejected: bool = Field(
        default=False,
        description="If true with user_input, re-run worker with feedback. If true without user_input, cancel task.",
    )


class TaskReject(BaseModel):
    """Request schema for rejecting a task at a breakpoint."""

    reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional reason for rejecting the task",
    )


class QAConfigRequest(BaseModel):
    """QA configuration update request."""

    validations: list[Literal["static", "lint", "typecheck", "test", "build"]] = Field(
        default=["static"],
        description="Validation types to enable",
    )
    test_command: str | None = Field(default=None, description="Custom test command")
    lint_command: str | None = Field(default=None, description="Custom lint command")
    typecheck_command: str | None = Field(default=None, description="Custom typecheck command")
    build_command: str | None = Field(default=None, description="Custom build command")
    allow_lint_warnings: bool = Field(
        default=True, description="Whether to allow lint warnings without failing"
    )
    require_all_tests_pass: bool = Field(
        default=True, description="Whether all tests must pass for QA to pass"
    )
