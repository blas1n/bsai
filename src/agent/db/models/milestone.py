"""Milestone model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, INTEGER, TEXT, VARCHAR, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import MilestoneStatus

if TYPE_CHECKING:
    from .agent_step import AgentStep
    from .artifact import Artifact
    from .generated_prompt import GeneratedPrompt
    from .llm_usage_log import LLMUsageLog
    from .task import Task


class Milestone(Base):
    """Individual task step with LLM assignment and QA tracking.

    Attributes:
        id: Primary key (UUID)
        task_id: Foreign key to tasks table
        sequence_number: Order within task (1, 2, 3...)
        title: Brief milestone title
        description: Detailed milestone description
        complexity: Task complexity level (trivial, simple, moderate, complex, context_heavy)
        acceptance_criteria: Criteria for milestone completion
        selected_llm: LLM model selected by Architect
        status: Milestone status (pending, in_progress, passed, failed)
        worker_output: Worker agent output
        qa_result: QA agent feedback/result
        retry_count: Number of retry attempts
        input_tokens: Input tokens consumed
        output_tokens: Output tokens consumed
        cost_usd: Cost in USD for this milestone
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "milestones"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence_number", name="uq_milestone_task_sequence"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    sequence_number: Mapped[int] = mapped_column(INTEGER)
    title: Mapped[str] = mapped_column(VARCHAR(255), default="")
    description: Mapped[str] = mapped_column(TEXT, default="")
    complexity: Mapped[str] = mapped_column(VARCHAR(20), index=True)
    acceptance_criteria: Mapped[str] = mapped_column(TEXT, default="")
    selected_llm: Mapped[str] = mapped_column(VARCHAR(100), default="")
    status: Mapped[str] = mapped_column(
        VARCHAR(20), default=MilestoneStatus.PENDING.value, index=True
    )
    worker_output: Mapped[str | None] = mapped_column(TEXT)
    qa_result: Mapped[str | None] = mapped_column(TEXT)
    retry_count: Mapped[int] = mapped_column(INTEGER, default=0)
    input_tokens: Mapped[int] = mapped_column(INTEGER, default=0)
    output_tokens: Mapped[int] = mapped_column(INTEGER, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(DECIMAL(10, 6), default=Decimal("0"))
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(INTEGER, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Relationships
    task: Mapped[Task] = relationship(back_populates="milestones")
    llm_usage_logs: Mapped[list[LLMUsageLog]] = relationship(
        back_populates="milestone", lazy="selectin", cascade="all, delete-orphan"
    )
    generated_prompts: Mapped[list[GeneratedPrompt]] = relationship(
        back_populates="milestone", lazy="selectin", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="milestone", lazy="selectin", cascade="all, delete-orphan"
    )
    agent_steps: Mapped[list[AgentStep]] = relationship(
        back_populates="milestone", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Milestone(id={self.id}, task_id={self.task_id}, status={self.status})>"
