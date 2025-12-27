"""Tests for LLMRouter."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from agent.db.models.enums import TaskComplexity
from agent.llm.models import LLMModel
from agent.llm.registry import ModelRegistry
from agent.llm.router import LLMRouter


@pytest.fixture
def mock_registry() -> MagicMock:
    """Create mock ModelRegistry."""
    registry = MagicMock(spec=ModelRegistry)

    # Mock models
    gpt4o_mini = LLMModel(
        name="gpt-4o-mini",
        provider="openai",
        input_price_per_1k=Decimal("0.00015"),
        output_price_per_1k=Decimal("0.0006"),
        context_window=128000,
        supports_streaming=True,
    )
    claude_sonnet = LLMModel(
        name="claude-3-5-sonnet-20241022",
        provider="anthropic",
        input_price_per_1k=Decimal("0.003"),
        output_price_per_1k=Decimal("0.015"),
        context_window=200000,
        supports_streaming=True,
    )

    def mock_get(name: str) -> LLMModel | None:
        models = {
            "gpt-4o-mini": gpt4o_mini,
            "claude-3-5-sonnet-20241022": claude_sonnet,
        }
        return models.get(name)

    registry.get = MagicMock(side_effect=mock_get)
    registry.get_all = MagicMock(
        return_value={"gpt-4o-mini": gpt4o_mini, "claude-3-5-sonnet-20241022": claude_sonnet}
    )

    return registry


@pytest.fixture
def router(mock_registry: MagicMock) -> LLMRouter:
    """Create LLMRouter instance."""
    complexity_mapping = {
        "TRIVIAL": "gpt-4o-mini",
        "SIMPLE": "gpt-4o-mini",
        "MODERATE": "claude-3-5-sonnet-20241022",
    }
    return LLMRouter(registry=mock_registry, complexity_mapping=complexity_mapping)


class TestLLMRouter:
    """Test LLMRouter functionality."""

    def test_select_model_by_complexity(self, router: LLMRouter, mock_registry: MagicMock) -> None:
        """Test model selection by complexity."""
        model = router.select_model(TaskComplexity.TRIVIAL)

        assert model.name == "gpt-4o-mini"
        mock_registry.get.assert_called_with("gpt-4o-mini")

    def test_select_model_with_preferred_model(
        self, router: LLMRouter, mock_registry: MagicMock
    ) -> None:
        """Test model selection with preferred model override."""
        model = router.select_model(
            TaskComplexity.TRIVIAL, preferred_model="claude-3-5-sonnet-20241022"
        )

        assert model.name == "claude-3-5-sonnet-20241022"
        mock_registry.get.assert_called_with("claude-3-5-sonnet-20241022")

    def test_select_model_fallback(self, mock_registry: MagicMock) -> None:
        """Test fallback to default model when complexity not mapped."""
        router = LLMRouter(registry=mock_registry)  # No mapping

        model = router.select_model(TaskComplexity.COMPLEX)

        # Should use fallback
        assert model.name == "gpt-4o-mini"

    def test_select_model_not_found_raises_error(self, mock_registry: MagicMock) -> None:
        """Test error when model not found in registry."""
        # Create new mock that always returns None
        mock_registry.get = MagicMock(return_value=None)
        mock_registry.get_all = MagicMock(return_value={})

        router = LLMRouter(registry=mock_registry)

        with pytest.raises(ValueError, match="not found in registry or LiteLLM"):
            router.select_model(TaskComplexity.TRIVIAL)

    def test_calculate_cost(self, router: LLMRouter) -> None:
        """Test cost calculation."""
        model = LLMModel(
            name="test-model",
            provider="test",
            input_price_per_1k=Decimal("0.001"),
            output_price_per_1k=Decimal("0.002"),
            context_window=1000,
            supports_streaming=True,
        )

        cost = router.calculate_cost(model, input_tokens=1000, output_tokens=500)

        # (1000 / 1000) * 0.001 + (500 / 1000) * 0.002 = 0.001 + 0.001 = 0.002
        assert cost == Decimal("0.002")

    def test_estimate_tokens_with_tiktoken(self, router: LLMRouter) -> None:
        """Test token estimation with tiktoken."""
        text = "Hello, world!"

        tokens = router.estimate_tokens(text)

        assert tokens > 0
        assert isinstance(tokens, int)

    def test_estimate_tokens_fallback(self, mock_registry: MagicMock) -> None:
        """Test token estimation fallback when tiktoken unavailable."""
        router = LLMRouter(registry=mock_registry)
        router.encoding = None  # Simulate tiktoken unavailable

        text = "Hello, world!"  # 13 characters
        tokens = router.estimate_tokens(text)

        # Fallback: len(text) // 4 = 13 // 4 = 3
        assert tokens == 3

    def test_set_complexity_mapping(self, router: LLMRouter, mock_registry: MagicMock) -> None:
        """Test dynamic complexity mapping update."""
        new_mapping = {"TRIVIAL": "claude-3-5-sonnet-20241022"}

        router.set_complexity_mapping(new_mapping)

        model = router.select_model(TaskComplexity.TRIVIAL)
        assert model.name == "claude-3-5-sonnet-20241022"
