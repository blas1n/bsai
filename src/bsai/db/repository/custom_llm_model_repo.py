"""Custom LLM model repository for user-defined model operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.custom_llm_model import CustomLLMModel
from .base import BaseRepository


class CustomLLMModelRepository(BaseRepository[CustomLLMModel]):
    """Repository for CustomLLMModel operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize custom LLM model repository.

        Args:
            session: Database session
        """
        super().__init__(CustomLLMModel, session)

    async def get_by_name(self, name: str) -> CustomLLMModel | None:
        """Get custom model by name.

        Args:
            name: Model name

        Returns:
            Custom LLM model if found, None otherwise
        """
        stmt = select(CustomLLMModel).where(CustomLLMModel.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_active(self) -> list[CustomLLMModel]:
        """Get all active custom models.

        Returns:
            List of all custom models ordered by creation date (newest first)
        """
        stmt = select(CustomLLMModel).order_by(CustomLLMModel.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
