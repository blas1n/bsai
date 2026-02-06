"""LLM client layer.

Lightweight LiteLLM wrapper for unified multi-provider LLM access with
cost tracking and model selection based on task complexity.

Pricing is loaded dynamically from LiteLLM API via ModelRegistry.
"""

from .client import LiteLLMClient
from .logger import LLMUsageLogger
from .models import FALLBACK_MODEL_NAME, LLMModel
from .registry import ModelRegistry
from .router import LLMRouter
from .schemas import ChatMessage, LLMRequest, LLMResponse, UsageInfo

__all__ = [
    # Client
    "LiteLLMClient",
    # Router
    "LLMRouter",
    # Logger
    "LLMUsageLogger",
    # Registry
    "ModelRegistry",
    # Models
    "LLMModel",
    "FALLBACK_MODEL_NAME",
    # Schemas
    "ChatMessage",
    "LLMRequest",
    "LLMResponse",
    "UsageInfo",
]
