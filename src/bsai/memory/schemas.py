"""Pydantic schemas for memory operations."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MemoryCreate(BaseModel):
    """Validation schema for creating memories.

    Attributes:
        user_id: Owner user ID (1-255 characters)
        session_id: Source session UUID
        content: Memory content text (1-100000 characters)
        memory_type: Classification of memory
        task_id: Optional source task UUID
        importance_score: Relevance weight (0.0-1.0)
        tags: Searchable tags (max 50 tags, each max 100 chars)
        metadata: Additional structured data
    """

    user_id: str = Field(..., min_length=1, max_length=255)
    session_id: UUID
    content: str = Field(..., min_length=1, max_length=100000)
    memory_type: str
    task_id: UUID | None = None
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] | None = Field(default=None, max_length=50)
    metadata: dict[str, Any] | None = None

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        """Validate user_id is not empty or whitespace.

        Args:
            v: User ID value

        Returns:
            Stripped user ID

        Raises:
            ValueError: If user_id is empty or whitespace
        """
        v = v.strip()
        if not v:
            raise ValueError("user_id cannot be empty or whitespace")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate content is not empty or whitespace.

        Args:
            v: Content value

        Returns:
            Content value (not stripped to preserve formatting)

        Raises:
            ValueError: If content is empty or whitespace only
        """
        if not v.strip():
            raise ValueError("content cannot be empty or whitespace only")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        """Validate tags list.

        Args:
            v: Tags list or None

        Returns:
            Validated tags list or None

        Raises:
            ValueError: If any tag exceeds 100 characters
        """
        if v is not None:
            for tag in v:
                if len(tag) > 100:
                    raise ValueError(f"Tag length cannot exceed 100 characters: {tag[:20]}...")
        return v
