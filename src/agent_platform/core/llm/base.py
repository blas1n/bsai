"""
Base LLM Provider Interface
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from pydantic import BaseModel


class ChatMessage(BaseModel):
    """Chat message"""

    role: str  # "user", "assistant", "system"
    content: str


class ChatRequest(BaseModel):
    """Chat completion request"""

    messages: list[ChatMessage]
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False


class UsageInfo(BaseModel):
    """Token usage information"""

    input_tokens: int
    output_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    """Chat completion response"""

    content: str
    role: str = "assistant"
    usage: UsageInfo
    model: str
    finish_reason: str


class ModelInfo(BaseModel):
    """Model information"""

    provider: str
    model_name: str
    context_window: int
    supports_streaming: bool


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """Generate chat completion"""
        pass

    @abstractmethod
    async def stream_completion(
        self, request: ChatRequest
    ) -> AsyncIterator[str]:
        """Stream chat completion"""
        pass

    @abstractmethod
    def get_token_count(self, text: str) -> int:
        """Count tokens in text"""
        pass

    @abstractmethod
    def get_model_info(self) -> ModelInfo:
        """Get model information"""
        pass
