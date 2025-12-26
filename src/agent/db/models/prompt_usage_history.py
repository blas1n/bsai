"""Prompt usage history model."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BOOLEAN, INTEGER, VARCHAR, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .generated_prompt import GeneratedPrompt
    from .milestone import Milestone
    from .system_prompt import SystemPrompt


class PromptUsageHistory(Base):
    """Tracks prompt effectiveness for optimization.

    Attributes:
        id: Primary key (UUID)
        milestone_id: Foreign key to milestones table
        system_prompt_id: Foreign key to system_prompts table (optional)
        generated_prompt_id: Foreign key to generated_prompts table (optional)
        final_prompt_hash: Hash of final combined prompt
        worker_llm: LLM model used by Worker
        qa_passed: Whether QA validation passed
        user_satisfaction: User satisfaction rating (1-5, optional)
        created_at: Creation timestamp
    """

    __tablename__ = "prompt_usage_history"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    milestone_id: Mapped[UUID] = mapped_column(ForeignKey("milestones.id"), index=True)
    system_prompt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("system_prompts.id"), index=True
    )
    generated_prompt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("generated_prompts.id"), index=True
    )
    final_prompt_hash: Mapped[str | None] = mapped_column(VARCHAR(64), index=True)
    worker_llm: Mapped[str | None] = mapped_column(VARCHAR(100))
    qa_passed: Mapped[bool | None] = mapped_column(BOOLEAN)
    user_satisfaction: Mapped[int | None] = mapped_column(INTEGER)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    milestone: Mapped["Milestone"] = relationship(
        back_populates="prompt_usage_history"
    )
    system_prompt: Mapped["SystemPrompt | None"] = relationship(
        back_populates="prompt_usage_history"
    )
    generated_prompt: Mapped["GeneratedPrompt | None"] = relationship(
        back_populates="generated_prompt"
    )

    def __repr__(self) -> str:
        return f"<PromptUsageHistory(id={self.id}, qa_passed={self.qa_passed})>"
