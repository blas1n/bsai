"""Async database session factory and utilities."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models.base import Base


class DatabaseSessionManager:
    """Manages database engine and session creation.

    This class follows the singleton pattern to ensure a single engine
    instance is shared across the application.

    Attributes:
        engine: SQLAlchemy async engine instance
        session_factory: Factory for creating async sessions
    """

    def __init__(
        self,
        database_url: str,
        pool_size: int = 10,
        max_overflow: int = 20,
        **engine_kwargs: Any,
    ) -> None:
        """Initialize database session manager.

        Args:
            database_url: PostgreSQL connection URL (must start with postgresql+asyncpg://)
            pool_size: Number of persistent connections in the pool
            max_overflow: Max additional connections beyond pool_size
            **engine_kwargs: Additional arguments passed to create_async_engine
        """
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # Verify connections before use
            pool_recycle=3600,  # Recycle connections after 1 hour
            **engine_kwargs,
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

    async def close(self) -> None:
        """Close database engine and all connections."""
        if self.engine:
            await self.engine.dispose()

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session.

        Yields:
            AsyncSession: Database session instance

        Example:
            async with session_manager.get_session() as session:
                result = await session.execute(select(User))
        """
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_all(self) -> None:
        """Create all tables defined in Base metadata.

        This should only be used for testing. In production,
        use Alembic migrations instead.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        """Drop all tables defined in Base metadata.

        WARNING: This will delete all data. Only use for testing.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# Global session manager instance (initialized via init_db())
session_manager: DatabaseSessionManager | None = None


def init_db(database_url: str) -> None:
    """Initialize the global database session manager.

    Args:
        database_url: PostgreSQL connection URL (must use asyncpg driver)

    Raises:
        RuntimeError: If already initialized
    """
    global session_manager
    if session_manager is not None:
        raise RuntimeError("DatabaseSessionManager already initialized")
    session_manager = DatabaseSessionManager(database_url)


async def close_db() -> None:
    """Close the global database session manager."""
    global session_manager
    if session_manager is not None:
        await session_manager.close()
        session_manager = None


def get_session_manager() -> DatabaseSessionManager:
    """Get the global session manager instance.

    Returns:
        DatabaseSessionManager: Global session manager

    Raises:
        RuntimeError: If session manager is not initialized
    """
    if session_manager is None:
        raise RuntimeError(
            "DatabaseSessionManager not initialized. "
            "Call init_db() first in your application startup."
        )
    return session_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for getting database sessions.

    Yields:
        AsyncSession: Database session instance

    Example:
        @app.get("/users")
        async def get_users(session: AsyncSession = Depends(get_db_session)):
            result = await session.execute(select(User))
            return result.scalars().all()
    """
    manager = get_session_manager()
    async for session in manager.get_session():
        yield session
