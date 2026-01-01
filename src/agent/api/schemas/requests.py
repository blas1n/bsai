"""Request schemas for API endpoints."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


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


class SnapshotCreate(BaseModel):
    """Request schema for creating a manual snapshot."""

    reason: str = Field(
        default="Manual checkpoint",
        max_length=500,
        description="Reason for creating the snapshot",
    )
