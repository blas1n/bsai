"""Task model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TEXT, VARCHAR, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import TaskStatus

if TYPE_CHECKING:
    from .agent_step import AgentStep
    from .artifact import Artifact
    from .episodic_memory import EpisodicMemory
    from .milestone import Milestone
    from .project_plan import ProjectPlan
    from .session import Session


class Task(Base):
    """User task with subdivision tracking.

    Attributes:
        id: Primary key (UUID)
        session_id: Foreign key to sessions table
        original_request: User's original task description
        status: Task status (pending, in_progress, completed, failed)
        final_result: Completed task output
        handover_context: Summary for next task's Conductor (milestones, artifacts)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    original_request: Mapped[str] = mapped_column(TEXT)
    status: Mapped[str] = mapped_column(VARCHAR(20), default=TaskStatus.PENDING.value, index=True)
    final_result: Mapped[str | None] = mapped_column(TEXT)
    handover_context: Mapped[str | None] = mapped_column(TEXT)  # Summary for next task's Conductor
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Relationships
    session: Mapped[Session] = relationship(back_populates="tasks")
    milestones: Mapped[list[Milestone]] = relationship(
        back_populates="task", lazy="selectin", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="task", lazy="selectin", cascade="all, delete-orphan"
    )
    agent_steps: Mapped[list[AgentStep]] = relationship(
        back_populates="task", lazy="selectin", cascade="all, delete-orphan"
    )
    episodic_memories: Mapped[list[EpisodicMemory]] = relationship(
        back_populates="task", lazy="selectin"
    )
    project_plan: Mapped[ProjectPlan | None] = relationship(back_populates="task", uselist=False)

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, status={self.status})>"
