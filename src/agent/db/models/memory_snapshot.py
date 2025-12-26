"""Memory snapshot model."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import INTEGER, TEXT, VARCHAR, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import SnapshotType

if TYPE_CHECKING:
    from .session import Session


class MemorySnapshot(Base):
    """Compressed context summaries for session resumption.

    Attributes:
        id: Primary key (UUID)
        session_id: Foreign key to sessions table
        snapshot_type: Type of snapshot (auto, manual, milestone)
        compressed_context: Compressed text summary
        key_decisions: Structured key decisions (JSON)
        token_count: Estimated token count of compressed context
        created_at: Creation timestamp
    """

    __tablename__ = "memory_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    snapshot_type: Mapped[str] = mapped_column(
        VARCHAR(30), default=SnapshotType.AUTO.value, index=True
    )
    compressed_context: Mapped[str] = mapped_column(TEXT)
    key_decisions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    token_count: Mapped[int] = mapped_column(INTEGER)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="memory_snapshots")

    def __repr__(self) -> str:
        return f"<MemorySnapshot(id={self.id}, type={self.snapshot_type})>"
