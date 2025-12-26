"""User settings model."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DECIMAL, INTEGER, VARCHAR, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserSettings(Base):
    """User-specific configuration for agent behavior.

    Attributes:
        id: Primary key (UUID)
        user_id: External user identifier
        qa_max_retries: Maximum QA retry attempts
        preferred_llm: Preferred LLM model name
        cost_limit_daily: Daily cost limit in USD
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "user_settings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[str | None] = mapped_column(VARCHAR(255), unique=True, index=True)
    qa_max_retries: Mapped[int] = mapped_column(INTEGER, default=3)
    preferred_llm: Mapped[str | None] = mapped_column(VARCHAR(100))
    cost_limit_daily: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 4))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<UserSettings(id={self.id}, user_id={self.user_id})>"
