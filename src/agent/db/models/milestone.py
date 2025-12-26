"""Milestone model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, INTEGER, TEXT, VARCHAR, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import MilestoneStatus

if TYPE_CHECKING:
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
        complexity: Task complexity level (trivial, simple, moderate, complex, context_heavy)
        selected_llm: LLM model selected by Conductor
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

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    sequence_number: Mapped[int] = mapped_column(INTEGER)
    title: Mapped[str] = mapped_column(VARCHAR(255))
    complexity: Mapped[str] = mapped_column(VARCHAR(20), index=True)
    selected_llm: Mapped[str] = mapped_column(VARCHAR(100))
    status: Mapped[str] = mapped_column(
        VARCHAR(20), default=MilestoneStatus.PENDING.value, index=True
    )
    worker_output: Mapped[str | None] = mapped_column(TEXT)
    qa_result: Mapped[str | None] = mapped_column(TEXT)
    retry_count: Mapped[int] = mapped_column(INTEGER, default=0)
    input_tokens: Mapped[int] = mapped_column(INTEGER, default=0)
    output_tokens: Mapped[int] = mapped_column(INTEGER, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(DECIMAL(10, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Relationships
    task: Mapped["Task"] = relationship(back_populates="milestones")
    llm_usage_logs: Mapped[list["LLMUsageLog"]] = relationship(
        back_populates="milestone", lazy="selectin"
    )
    generated_prompts: Mapped[list["GeneratedPrompt"]] = relationship(
        back_populates="milestone", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Milestone(id={self.id}, task_id={self.task_id}, status={self.status})>"
