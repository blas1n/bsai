"""System prompt model."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BOOLEAN, INTEGER, TEXT, VARCHAR, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .prompt_usage_history import PromptUsageHistory


class SystemPrompt(Base):
    """Versioned system prompts for agents.

    Attributes:
        id: Primary key (UUID)
        user_id: External user identifier (optional for global prompts)
        agent_type: Agent type (conductor, meta_prompter, worker, qa, summarizer)
        version: Version number (incremental)
        name: Prompt name/title
        content: Prompt template content
        is_active: Whether this version is active
        created_at: Creation timestamp
    """

    __tablename__ = "system_prompts"
    __table_args__ = (
        UniqueConstraint("user_id", "agent_type", "version", name="uq_user_agent_version"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[str | None] = mapped_column(VARCHAR(255), index=True)
    agent_type: Mapped[str] = mapped_column(VARCHAR(20), index=True)
    version: Mapped[int] = mapped_column(INTEGER)
    name: Mapped[str] = mapped_column(VARCHAR(255))
    content: Mapped[str] = mapped_column(TEXT)
    is_active: Mapped[bool] = mapped_column(BOOLEAN, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    prompt_usage_history: Mapped[list["PromptUsageHistory"]] = relationship(
        back_populates="system_prompt", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<SystemPrompt(id={self.id}, agent={self.agent_type}, v={self.version})>"
