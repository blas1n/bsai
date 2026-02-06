"""Project Plan database model.

Stores hierarchical project plans created by the Architect agent.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import TEXT, VARCHAR, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .session import Session
    from .task import Task


class ProjectPlan(Base):
    """Project plan with hierarchical structure.

    Stores the complete project plan including epics, features, and tasks
    in a JSONB column for flexibility.

    Attributes:
        id: Primary key (UUID)
        task_id: Foreign key to tasks table
        session_id: Foreign key to sessions table
        title: Project title
        overview: Project overview
        tech_stack: Technology stack list
        structure_type: Plan structure (flat, grouped, hierarchical)
        plan_data: Full hierarchical plan data as JSONB
        status: Plan status (draft, approved, in_progress, completed, rejected)
        approved_at: Approval timestamp
        approved_by: Approver identifier
        total_tasks: Total number of tasks
        completed_tasks: Number of completed tasks
        failed_tasks: Number of failed tasks
        breakpoint_config: Breakpoint configuration
        qa_config: QA configuration
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "project_plans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Foreign keys
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
    )
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
    )

    # Basic info
    title: Mapped[str] = mapped_column(VARCHAR(255))
    overview: Mapped[str | None] = mapped_column(TEXT)
    tech_stack: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # Structure
    structure_type: Mapped[str] = mapped_column(
        VARCHAR(20),
        default="flat",
    )  # flat, grouped, hierarchical

    # Full plan data as JSONB (epics, features, tasks)
    plan_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Status
    status: Mapped[str] = mapped_column(
        VARCHAR(20),
        default="draft",
        index=True,
    )  # draft, approved, in_progress, completed, rejected

    approved_at: Mapped[datetime | None] = mapped_column()
    approved_by: Mapped[str | None] = mapped_column(VARCHAR(255))

    # Progress tracking
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    failed_tasks: Mapped[int] = mapped_column(Integer, default=0)

    # Configuration
    breakpoint_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    qa_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Relationships
    task: Mapped[Task] = relationship(back_populates="project_plan")
    session: Mapped[Session] = relationship(back_populates="project_plans")

    def __repr__(self) -> str:
        return f"<ProjectPlan(id={self.id}, title={self.title}, status={self.status})>"

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100
