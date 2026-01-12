"""Agent step model for tracking individual agent executions within milestones."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, INTEGER, TEXT, VARCHAR, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .milestone import Milestone
    from .task import Task


class AgentStep(Base):
    """Individual agent execution step within a milestone.

    Tracks the timeline of agent executions for detailed monitoring,
    including which agent ran, when, and what it produced.

    Attributes:
        id: Primary key (UUID)
        task_id: Foreign key to tasks table
        milestone_id: Foreign key to milestones table (optional for task-level agents)
        agent_type: Type of agent (conductor, meta_prompter, worker, qa, summarizer)
        status: Execution status (started, completed, failed)
        started_at: When the agent started execution
        ended_at: When the agent finished execution
        duration_ms: Execution duration in milliseconds
        input_summary: Brief summary of input to the agent
        output_summary: Brief summary of agent output
        input_tokens: Tokens consumed for input
        output_tokens: Tokens generated
        cost_usd: Cost in USD for this step
        error_message: Error message if failed
        metadata: Additional JSON metadata
        created_at: Record creation timestamp
    """

    __tablename__ = "agent_steps"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    milestone_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("milestones.id"), index=True, nullable=True
    )
    agent_type: Mapped[str] = mapped_column(VARCHAR(50), index=True)
    status: Mapped[str] = mapped_column(VARCHAR(20), default="started", index=True)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(INTEGER, nullable=True)
    input_summary: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    input_tokens: Mapped[int] = mapped_column(INTEGER, default=0)
    output_tokens: Mapped[int] = mapped_column(INTEGER, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(DECIMAL(10, 6), default=Decimal("0"))
    error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    task: Mapped[Task] = relationship(back_populates="agent_steps")
    milestone: Mapped[Milestone | None] = relationship(back_populates="agent_steps")

    def __repr__(self) -> str:
        return f"<AgentStep(id={self.id}, agent_type={self.agent_type}, status={self.status})>"
