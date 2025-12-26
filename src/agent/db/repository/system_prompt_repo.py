"""System prompt repository for prompt management operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.system_prompt import SystemPrompt
from .base import BaseRepository


class SystemPromptRepository(BaseRepository[SystemPrompt]):
    """Repository for SystemPrompt model operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize system prompt repository.

        Args:
            session: Database session
        """
        super().__init__(SystemPrompt, session)

    async def get_active_prompt(self, agent_type: str, name: str) -> SystemPrompt | None:
        """Get the active prompt for an agent type and name.

        Args:
            agent_type: Agent type (conductor, meta_prompter, worker, qa, summarizer)
            name: Prompt name

        Returns:
            Active system prompt or None if not found
        """
        stmt = select(SystemPrompt).where(
            SystemPrompt.agent_type == agent_type,
            SystemPrompt.name == name,
            SystemPrompt.is_active == True,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name_and_version(self, name: str, version: int) -> SystemPrompt | None:
        """Get a specific prompt version.

        Args:
            name: Prompt name
            version: Version number

        Returns:
            System prompt or None if not found
        """
        stmt = select(SystemPrompt).where(
            SystemPrompt.name == name,
            SystemPrompt.version == version,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_versions(self, name: str) -> list[SystemPrompt]:
        """Get all versions of a prompt.

        Args:
            name: Prompt name

        Returns:
            List of system prompts ordered by version descending
        """
        stmt = (
            select(SystemPrompt)
            .where(SystemPrompt.name == name)
            .order_by(SystemPrompt.version.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_agent_type(self, agent_type: str) -> list[SystemPrompt]:
        """Get all prompts for an agent type.

        Args:
            agent_type: Agent type

        Returns:
            List of system prompts
        """
        stmt = (
            select(SystemPrompt)
            .where(SystemPrompt.agent_type == agent_type)
            .order_by(SystemPrompt.name.asc(), SystemPrompt.version.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
