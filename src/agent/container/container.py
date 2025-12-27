"""Dependency injection container for shared agent dependencies.

Provides singleton instances for:
- PromptManager
- LiteLLMClient
- ModelRegistry (requires async init)
- LLMRouter

Following the singleton pattern used in DatabaseSessionManager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from agent.llm import LiteLLMClient, LLMRouter, ModelRegistry
from agent.prompts import PromptManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class AgentContainer:
    """Singleton container for shared agent dependencies.

    Usage:
        container = get_container()
        await container.initialize(session)  # Call once at startup

        llm_client = container.llm_client
        router = container.router
    """

    _instance: AgentContainer | None = None
    _initialized: bool = False

    def __init__(self) -> None:
        """Initialize container with singletons."""
        self._prompt_manager: PromptManager | None = None
        self._llm_client: LiteLLMClient | None = None
        self._model_registry: ModelRegistry | None = None
        self._llm_router: LLMRouter | None = None

    @classmethod
    def get_instance(cls) -> AgentContainer:
        """Get or create singleton instance.

        Returns:
            The singleton AgentContainer instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance.

        Useful for testing to ensure clean state between tests.
        """
        if cls._instance is not None:
            cls._instance._initialized = False
            cls._instance._prompt_manager = None
            cls._instance._llm_client = None
            cls._instance._model_registry = None
            cls._instance._llm_router = None
        cls._instance = None

    async def initialize(self, session: AsyncSession | None = None) -> None:
        """Initialize async dependencies (call once at app startup).

        Args:
            session: Optional database session for ModelRegistry
                    to load custom models from database
        """
        if self._initialized:
            return

        # Create singletons
        self._prompt_manager = PromptManager()
        self._llm_client = LiteLLMClient()

        # ModelRegistry needs async init for custom models
        self._model_registry = ModelRegistry(session)
        await self._model_registry.initialize()

        # LLMRouter depends on registry
        self._llm_router = LLMRouter(self._model_registry)

        self._initialized = True
        logger.info("agent_container_initialized")

    @property
    def is_initialized(self) -> bool:
        """Check if container is initialized.

        Returns:
            True if initialize() has been called
        """
        return self._initialized

    @property
    def prompt_manager(self) -> PromptManager:
        """Get PromptManager singleton.

        Returns:
            PromptManager instance

        Raises:
            RuntimeError: If container not initialized
        """
        if self._prompt_manager is None:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        return self._prompt_manager

    @property
    def llm_client(self) -> LiteLLMClient:
        """Get LiteLLMClient singleton.

        Returns:
            LiteLLMClient instance

        Raises:
            RuntimeError: If container not initialized
        """
        if self._llm_client is None:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        return self._llm_client

    @property
    def model_registry(self) -> ModelRegistry:
        """Get ModelRegistry singleton.

        Returns:
            ModelRegistry instance

        Raises:
            RuntimeError: If container not initialized
        """
        if self._model_registry is None:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        return self._model_registry

    @property
    def router(self) -> LLMRouter:
        """Get LLMRouter singleton.

        Returns:
            LLMRouter instance

        Raises:
            RuntimeError: If container not initialized
        """
        if self._llm_router is None:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        return self._llm_router

    async def close(self) -> None:
        """Cleanup resources."""
        self._initialized = False
        logger.info("agent_container_closed")
