"""
LLM Provider Registry
"""

import structlog

logger = structlog.get_logger()


class LLMRegistry:
    """Central registry for LLM providers"""

    def __init__(self) -> None:
        self.providers: dict = {}

    async def initialize(self) -> None:
        """Initialize all LLM providers"""
        logger.info("initializing_llm_providers")
        # TODO: Initialize providers based on available API keys
        # from agent_platform.core.llm.providers.openai_provider import OpenAIProvider
        # self.providers["openai"] = OpenAIProvider()


# Global instance
llm_registry = LLMRegistry()
