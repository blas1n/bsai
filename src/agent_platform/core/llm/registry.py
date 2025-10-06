"""
LLM Provider Registry
"""

from typing import dict, list

import structlog

from agent_platform.core.llm.base import LLMProvider, ModelInfo


logger = structlog.get_logger()


class LLMRegistry:
    """Central registry for LLM providers"""

    def __init__(self) -> None:
        self.providers: dict[str, LLMProvider] = {}

    async def register(self, name: str, provider: LLMProvider) -> None:
        """
        Register an LLM provider.

        Args:
            name: Provider name (e.g., "openai", "anthropic")
            provider: Provider instance
        """
        self.providers[name] = provider
        logger.info("provider_registered", name=name)

    async def get_provider(self, name: str) -> LLMProvider:
        """
        Get a registered provider by name.

        Args:
            name: Provider name

        Returns:
            Provider instance

        Raises:
            KeyError: If provider not found
        """
        if name not in self.providers:
            raise KeyError(f"Provider '{name}' not found. Available: {list(self.providers.keys())}")
        return self.providers[name]

    async def list_models(self) -> list[ModelInfo]:
        """
        list all available models from all providers.

        Returns:
            list of model information
        """
        models = []
        for provider in self.providers.values():
            models.append(provider.get_model_info())
        return models

    async def initialize(self) -> None:
        """
        Initialize all LLM providers based on available API keys.

        This method attempts to initialize providers for which API keys
        are available in the environment. Providers without API keys
        are skipped.
        """
        logger.info("initializing_llm_providers")

        # Try to initialize OpenAI
        try:
            from agent_platform.core.llm.providers import OpenAIProvider

            provider = OpenAIProvider()
            await self.register("openai", provider)
            logger.info("openai_provider_registered")
        except ValueError as e:
            logger.warning("openai_provider_skipped", reason=str(e))

        # Try to initialize Anthropic
        try:
            from agent_platform.core.llm.providers import AnthropicProvider

            provider = AnthropicProvider()
            await self.register("anthropic", provider)
            logger.info("anthropic_provider_registered")
        except ValueError as e:
            logger.warning("anthropic_provider_skipped", reason=str(e))

        # Try to initialize Google Gemini
        try:
            from agent_platform.core.llm.providers import GoogleProvider

            provider = GoogleProvider()
            await self.register("google", provider)
            logger.info("google_provider_registered")
        except ValueError as e:
            logger.warning("google_provider_skipped", reason=str(e))

        # Always register LiteLLM as fallback (no API key required)
        try:
            from agent_platform.core.llm.providers import LiteLLMProvider

            provider = LiteLLMProvider()
            await self.register("litellm", provider)
            logger.info("litellm_provider_registered")
        except Exception as e:
            logger.warning("litellm_provider_skipped", reason=str(e))

        logger.info(
            "llm_providers_initialized",
            count=len(self.providers),
            providers=list(self.providers.keys()),
        )


# Global instance
llm_registry = LLMRegistry()
