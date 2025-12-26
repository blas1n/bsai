"""System prompt model."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BOOLEAN, INTEGER, TEXT, VARCHAR, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .generated_prompt import GeneratedPrompt


class SystemPrompt(Base):
    """Versioned system prompts for agents.

    Attributes:
        id: Primary key (UUID)
        name: Prompt name/title
        agent_type: Agent type (conductor, meta_prompter, worker, qa, summarizer)
        version: Version number (incremental)
        template: Prompt template content (Jinja2 format)
        is_active: Whether this version is active
        created_at: Creation timestamp
    """

    __tablename__ = "system_prompts"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_name_version"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(VARCHAR(255), index=True)
    agent_type: Mapped[str] = mapped_column(VARCHAR(20), index=True)
    version: Mapped[int] = mapped_column(INTEGER)
    template: Mapped[str] = mapped_column(TEXT)
    is_active: Mapped[bool] = mapped_column(BOOLEAN, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    generated_prompts: Mapped[list["GeneratedPrompt"]] = relationship(
        back_populates="system_prompt", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<SystemPrompt(id={self.id}, agent={self.agent_type}, v={self.version})>"
