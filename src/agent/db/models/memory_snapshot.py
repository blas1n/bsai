"""Memory snapshot model."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import INTEGER, TEXT, VARCHAR, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .milestone import Milestone
    from .session import Session


class MemorySnapshot(Base):
    """Compressed context summaries for session resumption.

    Attributes:
        id: Primary key (UUID)
        session_id: Foreign key to sessions table
        milestone_id: Foreign key to milestones table (optional)
        snapshot_type: Type of snapshot (milestone_complete, context_overflow, session_pause)
        summary: Compressed text summary
        key_decisions: Structured key decisions (JSON)
        artifacts: Code/file references (JSON)
        context_token_count: Estimated token count of original context
        created_at: Creation timestamp
    """

    __tablename__ = "memory_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    milestone_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("milestones.id"), index=True
    )
    snapshot_type: Mapped[str] = mapped_column(VARCHAR(30), index=True)
    summary: Mapped[str] = mapped_column(TEXT)
    key_decisions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    artifacts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    context_token_count: Mapped[int | None] = mapped_column(INTEGER)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="memory_snapshots")
    milestone: Mapped["Milestone | None"] = relationship(
        back_populates="memory_snapshots"
    )

    def __repr__(self) -> str:
        return f"<MemorySnapshot(id={self.id}, type={self.snapshot_type})>"
