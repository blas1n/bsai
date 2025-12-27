"""Tests for ModelRegistry."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.llm.registry import ModelRegistry


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    # session.add() is synchronous, not async
    session.add = MagicMock()
    return session


@pytest.fixture
def registry(mock_session: AsyncMock) -> ModelRegistry:
    """Create ModelRegistry instance."""
    return ModelRegistry(session=mock_session)


class TestModelRegistry:
    """Test ModelRegistry functionality."""

    @patch("agent.llm.registry.litellm.get_model_info")
    def test_load_from_litellm_success(
        self, mock_get_info: MagicMock, registry: ModelRegistry
    ) -> None:
        """Test loading model from LiteLLM API."""
        # Setup mock
        mock_get_info.return_value = {
            "litellm_provider": "openai",
            "input_cost_per_token": 0.00000015,
            "output_cost_per_token": 0.0000006,
            "max_input_tokens": 128000,
            "supports_streaming": True,
        }

        # Load model
        model = registry.load_from_litellm("gpt-4o-mini")

        # Verify
        assert model.name == "gpt-4o-mini"
        assert model.provider == "openai"
        assert model.input_price_per_1k == Decimal("0.00015")
        assert model.output_price_per_1k == Decimal("0.0006")
        assert model.context_window == 128000
        assert model.supports_streaming is True

    @patch("agent.llm.registry.litellm.get_model_info")
    def test_load_from_litellm_with_caching(
        self, mock_get_info: MagicMock, registry: ModelRegistry
    ) -> None:
        """Test that loaded models are cached."""
        mock_get_info.return_value = {
            "litellm_provider": "openai",
            "input_cost_per_token": 0.00000015,
            "output_cost_per_token": 0.0000006,
            "max_input_tokens": 128000,
            "supports_streaming": True,
        }

        # Load twice
        model1 = registry.load_from_litellm("gpt-4o-mini")
        model2 = registry.load_from_litellm("gpt-4o-mini")

        # Should be same instance (cached)
        assert model1 is model2
        # LiteLLM API called only once
        assert mock_get_info.call_count == 1

    @patch("agent.llm.registry.litellm.get_model_info")
    def test_load_from_litellm_missing_fields(
        self, mock_get_info: MagicMock, registry: ModelRegistry
    ) -> None:
        """Test loading model with missing optional fields."""
        mock_get_info.return_value = {
            "litellm_provider": "openai",
            "input_cost_per_token": 0.00000015,
            "output_cost_per_token": 0.0000006,
            # max_input_tokens missing
            # supports_streaming missing
        }

        model = registry.load_from_litellm("gpt-4o-mini")

        # Should use defaults
        assert model.context_window == 4096  # default
        assert model.supports_streaming is True  # default

    @patch("agent.llm.registry.litellm.get_model_info")
    def test_load_from_litellm_api_error(
        self, mock_get_info: MagicMock, registry: ModelRegistry
    ) -> None:
        """Test handling of LiteLLM API errors."""
        mock_get_info.side_effect = Exception("Model not found")

        with pytest.raises(ValueError, match="Failed to load model"):
            registry.load_from_litellm("unknown-model")

    def test_get_with_litellm_model(self, registry: ModelRegistry) -> None:
        """Test get() loads from LiteLLM on demand."""
        with patch("agent.llm.registry.litellm.get_model_info") as mock_get_info:
            mock_get_info.return_value = {
                "litellm_provider": "openai",
                "input_cost_per_token": 0.00000015,
                "output_cost_per_token": 0.0000006,
                "max_input_tokens": 128000,
                "supports_streaming": True,
            }

            model = registry.get("gpt-4o-mini")

            assert model is not None
            assert model.name == "gpt-4o-mini"

    def test_get_nonexistent_model(self, registry: ModelRegistry) -> None:
        """Test get() returns None for nonexistent model."""
        with patch("agent.llm.registry.litellm.get_model_info") as mock_get_info:
            mock_get_info.side_effect = Exception("Not found")

            model = registry.get("unknown-model")

            assert model is None

    async def test_add_custom_model(self, registry: ModelRegistry) -> None:
        """Test adding custom model."""
        await registry.add_custom_model(
            name="my-custom-model",
            provider="openai",
            input_price_per_1k=Decimal("0.001"),
            output_price_per_1k=Decimal("0.002"),
            context_window=8000,
            supports_streaming=True,
            api_base="https://api.example.com",
            api_key="test-key",
        )

        # Should be retrievable
        model = registry.get("my-custom-model")
        assert model is not None
        assert model.name == "my-custom-model"
        assert model.provider == "openai"
        assert model.api_base == "https://api.example.com"
        assert model.api_key == "test-key"

    async def test_custom_model_takes_precedence(self, registry: ModelRegistry) -> None:
        """Test custom models override LiteLLM models."""
        # Add custom model with same name
        await registry.add_custom_model(
            name="gpt-4o-mini",
            provider="custom",
            input_price_per_1k=Decimal("0.999"),
            output_price_per_1k=Decimal("0.999"),
            context_window=1000,
        )

        # Should get custom model, not LiteLLM one
        model = registry.get("gpt-4o-mini")
        assert model is not None
        assert model.provider == "custom"
        assert model.input_price_per_1k == Decimal("0.999")

    def test_get_all_models(self, registry: ModelRegistry) -> None:
        """Test get_all() returns all models."""
        with patch("agent.llm.registry.litellm.get_model_info") as mock_get_info:
            # Mock return value
            mock_get_info.return_value = {
                "litellm_provider": "openai",
                "input_cost_per_token": 0.00000015,
                "output_cost_per_token": 0.0000006,
                "max_input_tokens": 128000,
                "supports_streaming": True,
            }

            # Add some models
            registry.load_from_litellm("model1")

            all_models = registry.get_all()

            assert "model1" in all_models
