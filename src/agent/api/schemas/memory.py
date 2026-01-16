"""Pydantic schemas for memory API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MemoryResponse(BaseModel):
    """Single memory response."""

    id: UUID
    user_id: str
    session_id: UUID
    task_id: UUID | None = None
    summary: str
    memory_type: str
    importance_score: float = Field(ge=0.0, le=1.0)
    access_count: int = 0
    tags: list[str] | None = None
    created_at: datetime
    last_accessed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MemoryDetailResponse(MemoryResponse):
    """Detailed memory response with full content."""

    content: str
    metadata_json: dict[str, Any] | None = None


class MemorySearchResult(BaseModel):
    """Memory with similarity score."""

    memory: MemoryResponse
    similarity: float = Field(ge=0.0, le=1.0)


class MemorySearchRequest(BaseModel):
    """Search request parameters."""

    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    memory_types: list[str] | None = None
    min_similarity: float = Field(default=0.7, ge=0.0, le=1.0)


class ConsolidateResult(BaseModel):
    """Memory consolidation result."""

    consolidated_count: int
    remaining_count: int


class DecayResult(BaseModel):
    """Memory decay result."""

    decayed_count: int


class MemoryStatsResponse(BaseModel):
    """Memory statistics for user."""

    total_memories: int
    by_type: dict[str, int]
    average_importance: float
