"""LLM request/response schemas.

Type-safe Pydantic models for LLM interactions.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Individual chat message."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    """LLM completion request."""

    model: str
    messages: list[ChatMessage]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = None
    stream: bool = False
    api_base: str | None = None
    api_key: str | None = None


class UsageInfo(BaseModel):
    """Token usage information."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class LLMResponse(BaseModel):
    """LLM completion response."""

    content: str
    usage: UsageInfo
    model: str
    finish_reason: str | None = None
