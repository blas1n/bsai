"""User settings repository for user configuration operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user_settings import UserSettings
from .base import BaseRepository


class UserSettingsRepository(BaseRepository[UserSettings]):
    """Repository for UserSettings model operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize user settings repository.

        Args:
            session: Database session
        """
        super().__init__(UserSettings, session)

    async def get_by_user_id(self, user_id: str) -> UserSettings | None:
        """Get settings by user ID.

        Args:
            user_id: External user identifier

        Returns:
            User settings or None if not found
        """
        stmt = select(UserSettings).where(UserSettings.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: str) -> UserSettings:
        """Get or create user settings with defaults.

        Args:
            user_id: External user identifier

        Returns:
            User settings (existing or newly created)
        """
        settings = await self.get_by_user_id(user_id)
        if settings is not None:
            return settings

        # Create with defaults
        settings = await self.create(user_id=user_id)
        await self.session.flush()
        await self.session.refresh(settings)
        return settings

    async def update_preferences(
        self, user_id: str, **kwargs: str | int | float | None
    ) -> UserSettings | None:
        """Update user preferences.

        Args:
            user_id: External user identifier
            **kwargs: Settings to update

        Returns:
            Updated user settings or None if not found
        """
        settings = await self.get_by_user_id(user_id)
        if settings is None:
            return None

        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)

        await self.session.flush()
        await self.session.refresh(settings)
        return settings
