"""FastAPI dependencies for dependency injection."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agent.cache import RedisClient, SessionCache, get_redis
from agent.db.session import get_db_session

from .auth import get_current_user_id


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency.

    Yields:
        AsyncSession for database operations
    """
    async for session in get_db_session():
        yield session


def get_cache(
    redis_client: RedisClient = Depends(get_redis),
) -> SessionCache:
    """Session cache dependency.

    Args:
        redis_client: Redis client from DI

    Returns:
        SessionCache instance
    """
    return SessionCache(redis_client)


# Type aliases for cleaner route signatures
DBSession = Annotated[AsyncSession, Depends(get_db)]
Cache = Annotated[SessionCache, Depends(get_cache)]
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
