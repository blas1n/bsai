"""Generated prompt repository for meta prompter output operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.generated_prompt import GeneratedPrompt
from .base import BaseRepository


class GeneratedPromptRepository(BaseRepository[GeneratedPrompt]):
    """Repository for GeneratedPrompt model operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize generated prompt repository.

        Args:
            session: Database session
        """
        super().__init__(GeneratedPrompt, session)

    async def get_by_milestone(self, milestone_id: UUID) -> GeneratedPrompt | None:
        """Get generated prompt for a milestone.

        Args:
            milestone_id: Milestone UUID

        Returns:
            Generated prompt or None if not found
        """
        stmt = select(GeneratedPrompt).where(GeneratedPrompt.milestone_id == milestone_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_system_prompt(
        self, system_prompt_id: UUID, limit: int = 50
    ) -> list[GeneratedPrompt]:
        """Get all prompts generated from a system prompt.

        Args:
            system_prompt_id: System prompt UUID
            limit: Maximum number of prompts to return

        Returns:
            List of generated prompts
        """
        stmt = (
            select(GeneratedPrompt)
            .where(GeneratedPrompt.system_prompt_id == system_prompt_id)
            .order_by(GeneratedPrompt.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
