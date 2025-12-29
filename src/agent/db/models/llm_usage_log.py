"""LLM usage log model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, INTEGER, VARCHAR, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .milestone import Milestone
    from .session import Session


class LLMUsageLog(Base):
    """Detailed LLM API call tracking with cost calculation.

    Attributes:
        id: Primary key (UUID)
        session_id: Foreign key to sessions table
        milestone_id: Foreign key to milestones table (optional)
        agent_type: Agent that made the call (conductor, meta_prompter, worker, qa, summarizer)
        llm_provider: LLM provider (openai, anthropic, google)
        llm_model: Specific model name
        input_tokens: Input token count
        output_tokens: Output token count
        cost: Cost in USD
        latency_ms: API call latency in milliseconds
        created_at: Creation timestamp
    """

    __tablename__ = "llm_usage_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    milestone_id: Mapped[UUID | None] = mapped_column(ForeignKey("milestones.id"), index=True)
    agent_type: Mapped[str] = mapped_column(VARCHAR(20), index=True)
    llm_provider: Mapped[str] = mapped_column(VARCHAR(50), index=True)
    llm_model: Mapped[str] = mapped_column(VARCHAR(100), index=True)
    input_tokens: Mapped[int] = mapped_column(INTEGER)
    output_tokens: Mapped[int] = mapped_column(INTEGER)
    cost: Mapped[Decimal] = mapped_column(DECIMAL(10, 6))
    latency_ms: Mapped[int | None] = mapped_column(INTEGER)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="llm_usage_logs")
    milestone: Mapped["Milestone | None"] = relationship(back_populates="llm_usage_logs")

    def __repr__(self) -> str:
        return f"<LLMUsageLog(id={self.id}, model={self.llm_model}, cost={self.cost})>"
