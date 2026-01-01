"""Dependency injection container for shared agent dependencies.

Provides singleton instances for:
- PromptManager
- LiteLLMClient
- ModelRegistry (requires async init)
- LLMRouter

Uses context manager pattern for clean lifecycle management.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from agent.llm import LiteLLMClient, LLMRouter, ModelRegistry
from agent.prompts import PromptManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


@dataclass(frozen=True)
class ContainerState:
    """Immutable container holding initialized dependencies.

    All fields are required - state is only created when fully initialized.
    """

    prompt_manager: PromptManager
    llm_client: LiteLLMClient
    model_registry: ModelRegistry
    router: LLMRouter


@asynccontextmanager
async def lifespan(
    session: AsyncSession | None = None,
) -> AsyncIterator[ContainerState]:
    """Context manager for container lifecycle.

    Initializes dependencies on enter, closes on exit.

    Args:
        session: Optional database session for ModelRegistry

    Yields:
        The initialized container state

    Example:
        async with lifespan(session) as container:
            agent = WorkerAgent(
                llm_client=container.llm_client,
                router=container.router,
                session=session,
            )
    """
    model_registry = ModelRegistry(session)
    await model_registry.initialize()

    state = ContainerState(
        prompt_manager=PromptManager(),
        llm_client=LiteLLMClient(),
        model_registry=model_registry,
        router=LLMRouter(model_registry),
    )

    logger.info("agent_container_initialized")

    try:
        yield state
    finally:
        logger.info("agent_container_closed")
