"""LLM router for model selection and cost calculation.

Selects optimal LLM based on task complexity and calculates costs.
"""

from decimal import Decimal

import tiktoken
from tiktoken import Encoding

from agent.db.models.enums import TaskComplexity

from .models import FALLBACK_MODEL_NAME, LLMModel
from .registry import ModelRegistry


class LLMRouter:
    """Router for selecting optimal LLM based on task complexity."""

    def __init__(
        self,
        registry: ModelRegistry,
        complexity_mapping: dict[str, str] | None = None,
    ) -> None:
        """Initialize LLM router.

        Args:
            registry: Model registry with pricing data
            complexity_mapping: Optional complexity-to-model-name mapping from user settings.
                              Key is TaskComplexity enum name (e.g., "MODERATE").
                              If None, uses fallback model for all complexities.
        """
        self.registry = registry
        self.complexity_mapping = complexity_mapping or {}

        # Token encoding for estimation (using OpenAI's cl100k_base)
        self.encoding: Encoding | None
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # Fallback if tiktoken has issues
            self.encoding = None

    def select_model(
        self,
        complexity: TaskComplexity,
        preferred_model: str | None = None,
    ) -> LLMModel:
        """Select optimal LLM based on complexity.

        Args:
            complexity: Task complexity level (TaskComplexity enum)
            preferred_model: Optional user-preferred model name override

        Returns:
            Selected LLM model

        Raises:
            ValueError: If model not found in registry
        """
        # Determine model name
        if preferred_model is not None:
            model_name = preferred_model
        else:
            # Use complexity mapping or fallback
            model_name = self.complexity_mapping.get(complexity.name, FALLBACK_MODEL_NAME)

        # Load from registry
        model = self.registry.get(model_name)
        if model is None:
            raise ValueError(
                f"Model '{model_name}' not found in registry or LiteLLM. "
                f"Available custom models: {list(self.registry.get_all().keys())}"
            )

        return model

    def set_complexity_mapping(
        self,
        mapping: dict[str, str],
    ) -> None:
        """Dynamically update complexity to model mapping.

        Args:
            mapping: New complexity-to-model-name mapping.
                    Key is TaskComplexity enum name (e.g., "MODERATE").
        """
        self.complexity_mapping = mapping.copy()

    def calculate_cost(
        self,
        model: LLMModel,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """Calculate cost for given token usage.

        Args:
            model: LLM model used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Total cost in USD
        """
        input_cost = (Decimal(input_tokens) / Decimal("1000")) * model.input_price_per_1k
        output_cost = (Decimal(output_tokens) / Decimal("1000")) * model.output_price_per_1k
        return input_cost + output_cost

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using tiktoken.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated number of tokens
        """
        if self.encoding is None:
            # Fallback: rough estimate (1 token ≈ 4 characters)
            return len(text) // 4

        return len(self.encoding.encode(text))
