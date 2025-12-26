"""Prompt usage history model."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BOOLEAN, INTEGER, TEXT, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .generated_prompt import GeneratedPrompt


class PromptUsageHistory(Base):
    """Tracks prompt effectiveness for optimization.

    Attributes:
        id: Primary key (UUID)
        generated_prompt_id: Foreign key to generated_prompts table
        success: Whether execution was successful
        qa_passed: Whether QA validation passed
        retry_count: Number of retries needed
        feedback: QA feedback text (optional)
        created_at: Creation timestamp
    """

    __tablename__ = "prompt_usage_history"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    generated_prompt_id: Mapped[UUID] = mapped_column(
        ForeignKey("generated_prompts.id"), index=True
    )
    success: Mapped[bool] = mapped_column(BOOLEAN)
    qa_passed: Mapped[bool] = mapped_column(BOOLEAN)
    retry_count: Mapped[int] = mapped_column(INTEGER, default=0)
    feedback: Mapped[str | None] = mapped_column(TEXT)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    generated_prompt: Mapped["GeneratedPrompt"] = relationship()

    def __repr__(self) -> str:
        return f"<PromptUsageHistory(id={self.id}, qa_passed={self.qa_passed})>"
