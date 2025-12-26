"""LLM model definitions.

Defines LLMModel dataclass.
Pricing is loaded dynamically from LiteLLM via ModelRegistry.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class LLMModel:
    """LLM model configuration with pricing.

    Note: Do not instantiate directly. Use ModelRegistry to get models
    with pricing loaded from LiteLLM or database.
    """

    name: str  # Model name for API calls
    provider: str  # Provider: openai, anthropic, google, custom
    input_price_per_1k: Decimal  # USD per 1k input tokens
    output_price_per_1k: Decimal  # USD per 1k output tokens
    context_window: int  # Maximum context tokens
    supports_streaming: bool
    api_base: str | None = None  # Optional custom API base URL
    api_key: str | None = None  # Optional custom API key


# Fallback model name (used when no model is available)
FALLBACK_MODEL_NAME = "gpt-4o-mini"
