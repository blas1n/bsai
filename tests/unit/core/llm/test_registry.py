"""
Tests for LLM Provider Registry
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_platform.core.llm.base import ModelInfo
from agent_platform.core.llm.registry import LLMRegistry


class TestLLMRegistry:
    """Test LLM provider registry"""

    @pytest.fixture
    def registry(self):
        """Create fresh registry for each test"""
        return LLMRegistry()

    @pytest.fixture
    def mock_provider(self):
        """Create mock LLM provider"""
        provider = MagicMock()
        provider.get_model_info.return_value = ModelInfo(
            provider="test",
            model_name="test-model",
            context_window=8192,
            supports_streaming=True,
        )
        return provider

    @pytest.mark.asyncio
    async def test_register_provider(self, registry, mock_provider):
        """Test registering a provider"""
        # Register provider
        await registry.register("test", mock_provider)

        # Verify it was registered
        assert "test" in registry.providers
        assert registry.providers["test"] == mock_provider

    @pytest.mark.asyncio
    async def test_get_provider(self, registry, mock_provider):
        """Test getting a registered provider"""
        # Register provider first
        await registry.register("test", mock_provider)

        # Get provider
        provider = await registry.get_provider("test")

        assert provider == mock_provider

    @pytest.mark.asyncio
    async def test_get_provider_not_found(self, registry):
        """Test getting non-existent provider raises error"""
        with pytest.raises(KeyError, match="Provider 'nonexistent' not found"):
            await registry.get_provider("nonexistent")

    @pytest.mark.asyncio
    async def test_list_models(self, registry, mock_provider):
        """Test listing all available models"""
        # Register provider
        await registry.register("test", mock_provider)

        # List models
        models = await registry.list_models()

        assert len(models) == 1
        assert models[0].provider == "test"
        assert models[0].model_name == "test-model"

    @pytest.mark.asyncio
    async def test_list_models_multiple_providers(self, registry):
        """Test listing models from multiple providers"""
        # Create mock providers
        provider1 = MagicMock()
        provider1.get_model_info.return_value = ModelInfo(
            provider="openai",
            model_name="gpt-4",
            context_window=8192,
            supports_streaming=True,
        )

        provider2 = MagicMock()
        provider2.get_model_info.return_value = ModelInfo(
            provider="anthropic",
            model_name="claude-3-opus",
            context_window=200000,
            supports_streaming=True,
        )

        # Register providers
        await registry.register("openai", provider1)
        await registry.register("anthropic", provider2)

        # List models
        models = await registry.list_models()

        assert len(models) == 2
        assert any(m.provider == "openai" for m in models)
        assert any(m.provider == "anthropic" for m in models)

    @pytest.mark.asyncio
    async def test_initialize_with_api_keys(self, registry):
        """Test initialization registers providers based on available API keys"""
        env_vars = {
            "OPENAI_API_KEY": "test-openai-key",
            "ANTHROPIC_API_KEY": "test-anthropic-key",
            "GOOGLE_API_KEY": "test-google-key",
        }

        with patch.dict("os.environ", env_vars):
            with patch("agent_platform.core.llm.providers.OpenAIProvider") as mock_openai:
                with patch("agent_platform.core.llm.providers.AnthropicProvider") as mock_anthropic:
                    with patch("agent_platform.core.llm.providers.GoogleProvider") as mock_google:
                        with patch("agent_platform.core.llm.providers.LiteLLMProvider") as mock_litellm:
                            # Initialize registry
                            await registry.initialize()

                            # Verify providers were initialized
                            mock_openai.assert_called_once()
                            mock_anthropic.assert_called_once()
                            mock_google.assert_called_once()
                            mock_litellm.assert_called_once()

                            # Verify providers were registered
                            assert "openai" in registry.providers
                            assert "anthropic" in registry.providers
                            assert "google" in registry.providers
                            assert "litellm" in registry.providers

    @pytest.mark.asyncio
    async def test_initialize_partial_api_keys(self, registry):
        """Test initialization with only some API keys available"""
        env_vars = {
            "OPENAI_API_KEY": "test-openai-key",
            # ANTHROPIC_API_KEY and GOOGLE_API_KEY are missing
        }

        with patch.dict("os.environ", env_vars, clear=True):
            with patch("agent_platform.core.llm.providers.OpenAIProvider") as mock_openai:
                with patch("agent_platform.core.llm.providers.AnthropicProvider") as mock_anthropic:
                    with patch("agent_platform.core.llm.providers.GoogleProvider") as mock_google:
                        with patch("agent_platform.core.llm.providers.LiteLLMProvider") as mock_litellm:
                            # Make Anthropic and Google raise ValueError when no API key
                            mock_anthropic.side_effect = ValueError("ANTHROPIC_API_KEY not found")
                            mock_google.side_effect = ValueError("GOOGLE_API_KEY not found")

                            # Initialize registry
                            await registry.initialize()

                            # Verify all were attempted
                            mock_openai.assert_called_once()
                            mock_anthropic.assert_called_once()
                            mock_google.assert_called_once()
                            mock_litellm.assert_called_once()

                            # Verify only OpenAI and LiteLLM were registered
                            assert "openai" in registry.providers
                            assert "anthropic" not in registry.providers
                            assert "google" not in registry.providers
                            assert "litellm" in registry.providers  # Always registered

    @pytest.mark.asyncio
    async def test_initialize_no_api_keys(self, registry):
        """Test initialization with no API keys"""
        with patch.dict("os.environ", {}, clear=True):
            with patch("agent_platform.core.llm.providers.OpenAIProvider") as mock_openai:
                with patch("agent_platform.core.llm.providers.AnthropicProvider") as mock_anthropic:
                    with patch("agent_platform.core.llm.providers.GoogleProvider") as mock_google:
                        with patch("agent_platform.core.llm.providers.LiteLLMProvider") as mock_litellm:
                            # All API-key based providers should raise ValueError
                            mock_openai.side_effect = ValueError("OPENAI_API_KEY not found")
                            mock_anthropic.side_effect = ValueError("ANTHROPIC_API_KEY not found")
                            mock_google.side_effect = ValueError("GOOGLE_API_KEY not found")

                            # Initialize registry
                            await registry.initialize()

                            # Verify only LiteLLM was registered (doesn't require API key)
                            assert len(registry.providers) == 1
                            assert "litellm" in registry.providers
