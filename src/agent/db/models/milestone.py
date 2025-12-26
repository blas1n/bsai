"""Milestone model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BOOLEAN, DECIMAL, INTEGER, TEXT, VARCHAR, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .generated_prompt import GeneratedPrompt
    from .llm_usage_log import LLMUsageLog
    from .memory_snapshot import MemorySnapshot
    from .prompt_usage_history import PromptUsageHistory
    from .task import Task


class Milestone(Base):
    """Individual task step with LLM assignment and QA tracking.

    Attributes:
        id: Primary key (UUID)
        task_id: Foreign key to tasks table
        sequence_order: Order within task (1, 2, 3...)
        description: Milestone description
        complexity: Task complexity level (trivial, simple, moderate, complex, context_heavy)
        task_type: Type of task (generation, debugging, analysis, etc.)
        assigned_llm: LLM model assigned by Conductor
        status: Milestone status (pending, in_progress, completed, failed)
        worker_result: Worker agent output
        qa_passed: Whether QA validation passed
        qa_feedback: QA agent feedback
        qa_attempts: Number of QA attempts
        tokens_used: Tokens consumed for this milestone
        cost: Cost in USD for this milestone
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "milestones"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    sequence_order: Mapped[int] = mapped_column(INTEGER)
    description: Mapped[str] = mapped_column(TEXT)
    complexity: Mapped[str] = mapped_column(VARCHAR(20), index=True)
    task_type: Mapped[str] = mapped_column(VARCHAR(20))
    assigned_llm: Mapped[str | None] = mapped_column(VARCHAR(100))
    status: Mapped[str] = mapped_column(VARCHAR(20), default="pending", index=True)
    worker_result: Mapped[str | None] = mapped_column(TEXT)
    qa_passed: Mapped[bool | None] = mapped_column(BOOLEAN)
    qa_feedback: Mapped[str | None] = mapped_column(TEXT)
    qa_attempts: Mapped[int] = mapped_column(INTEGER, default=0)
    tokens_used: Mapped[int] = mapped_column(INTEGER, default=0)
    cost: Mapped[Decimal] = mapped_column(DECIMAL(10, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Relationships
    task: Mapped["Task"] = relationship(back_populates="milestones")
    memory_snapshots: Mapped[list["MemorySnapshot"]] = relationship(
        back_populates="milestone", lazy="selectin"
    )
    llm_usage_logs: Mapped[list["LLMUsageLog"]] = relationship(
        back_populates="milestone", lazy="selectin"
    )
    generated_prompts: Mapped[list["GeneratedPrompt"]] = relationship(
        back_populates="milestone", lazy="selectin"
    )
    prompt_usage_history: Mapped[list["PromptUsageHistory"]] = relationship(
        back_populates="milestone", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Milestone(id={self.id}, task_id={self.task_id}, status={self.status})>"
