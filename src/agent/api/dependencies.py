"""FastAPI dependencies for dependency injection."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agent.cache import SessionCache, get_redis
from agent.db.session import get_db_session

from .auth import get_current_user_id
from .websocket import ConnectionManager


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency.

    Yields:
        AsyncSession for database operations
    """
    async for session in get_db_session():
        yield session


def get_cache() -> SessionCache:
    """Session cache dependency for FastAPI DI.

    Returns:
        SessionCache instance
    """
    return SessionCache(get_redis())


def get_ws_manager(request: Request) -> ConnectionManager:
    """Get WebSocket connection manager from app state.

    Args:
        request: FastAPI request

    Returns:
        ConnectionManager instance
    """
    return request.app.state.ws_manager


# Type aliases for cleaner route signatures
DBSession = Annotated[AsyncSession, Depends(get_db)]
Cache = Annotated[SessionCache, Depends(get_cache)]
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
WSManager = Annotated[ConnectionManager, Depends(get_ws_manager)]
