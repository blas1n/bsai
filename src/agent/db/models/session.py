"""Session model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, INTEGER, VARCHAR, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .llm_usage_log import LLMUsageLog
    from .memory_snapshot import MemorySnapshot
    from .task import Task


class Session(Base):
    """Agent session tracking with cost aggregation.

    Attributes:
        id: Primary key (UUID)
        user_id: External user identifier
        status: Session status (active, paused, completed)
        total_tokens_used: Cumulative token count
        total_cost: Cumulative cost in USD
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[str | None] = mapped_column(VARCHAR(255), index=True)
    status: Mapped[str] = mapped_column(VARCHAR(20), default="active", index=True)
    total_tokens_used: Mapped[int] = mapped_column(INTEGER, default=0)
    total_cost: Mapped[Decimal] = mapped_column(DECIMAL(10, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="session", lazy="selectin"
    )
    memory_snapshots: Mapped[list["MemorySnapshot"]] = relationship(
        back_populates="session", lazy="selectin"
    )
    llm_usage_logs: Mapped[list["LLMUsageLog"]] = relationship(
        back_populates="session", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Session(id={self.id}, status={self.status})>"
