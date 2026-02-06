"""Custom LLM model definition for user-defined models."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import BOOLEAN, DECIMAL, INTEGER, VARCHAR, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CustomLLMModel(Base):
    """User-defined custom LLM models.

    Allows users to add custom models (self-hosted, fine-tuned, etc.)
    with their own pricing configurations.

    Attributes:
        id: Primary key (UUID)
        name: Unique model name/identifier
        provider: Provider name (openai, anthropic, custom, etc.)
        input_price_per_1k: Cost per 1000 input tokens (USD)
        output_price_per_1k: Cost per 1000 output tokens (USD)
        context_window: Maximum context window size
        supports_streaming: Whether the model supports streaming responses
        api_base: Optional custom API base URL (for self-hosted models)
        api_key: Optional custom API key (for self-hosted models)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "custom_llm_models"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(VARCHAR(100), unique=True, index=True)
    provider: Mapped[str] = mapped_column(VARCHAR(50))
    input_price_per_1k: Mapped[Decimal] = mapped_column(DECIMAL(12, 8))
    output_price_per_1k: Mapped[Decimal] = mapped_column(DECIMAL(12, 8))
    context_window: Mapped[int] = mapped_column(INTEGER)
    supports_streaming: Mapped[bool] = mapped_column(BOOLEAN, default=True)
    api_base: Mapped[str | None] = mapped_column(VARCHAR(500), nullable=True)
    api_key: Mapped[str | None] = mapped_column(VARCHAR(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<CustomLLMModel(id={self.id}, name='{self.name}', " f"provider='{self.provider}')>"
