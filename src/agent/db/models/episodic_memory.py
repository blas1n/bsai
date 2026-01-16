"""Episodic memory model for long-term semantic storage."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, FLOAT, INTEGER, TEXT, VARCHAR, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import MemoryType

if TYPE_CHECKING:
    from .session import Session
    from .task import Task


class EpisodicMemory(Base):
    """Long-term episodic memory for semantic search.

    Stores past experiences with vector embeddings for similarity search.

    Attributes:
        id: Primary key (UUID)
        user_id: Owner user ID (indexed for filtering)
        session_id: Source session FK
        task_id: Source task FK (optional)
        content: Original text content
        summary: Summarized content for display
        embedding: Vector embedding (1536 dimensions for ada-002)
        memory_type: Classification of memory
        importance_score: Relevance weight (0.0-1.0)
        access_count: Times retrieved
        tags: Searchable tags
        metadata: Additional structured data
        created_at: Creation timestamp
        last_accessed_at: Most recent access
    """

    __tablename__ = "episodic_memories"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(VARCHAR(255), index=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"))

    # Memory content
    content: Mapped[str] = mapped_column(TEXT)
    summary: Mapped[str] = mapped_column(TEXT)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))

    # Metadata
    memory_type: Mapped[str] = mapped_column(
        VARCHAR(50), default=MemoryType.TASK_RESULT.value, index=True
    )
    importance_score: Mapped[float] = mapped_column(FLOAT, default=0.5)
    access_count: Mapped[int] = mapped_column(INTEGER, default=0)

    # Context
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(VARCHAR(100)))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_accessed_at: Mapped[datetime | None] = mapped_column()

    # Relationships
    session: Mapped[Session] = relationship(back_populates="episodic_memories")
    task: Mapped[Task | None] = relationship(back_populates="episodic_memories")

    def __repr__(self) -> str:
        return f"<EpisodicMemory(id={self.id}, type={self.memory_type})>"
