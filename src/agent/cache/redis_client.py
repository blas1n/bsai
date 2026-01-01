"""Async Redis client with FastAPI DI support.

Provides connection pooling and lifecycle management for Redis.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import redis.asyncio as redis
import structlog

from agent.api.config import get_cache_settings

logger = structlog.get_logger()


class RedisClient:
    """Async Redis client wrapper with connection pooling."""

    def __init__(self, redis_url: str, max_connections: int = 20) -> None:
        """Initialize Redis client.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
            max_connections: Maximum pool connections
        """
        self.redis_url = redis_url
        self.max_connections = max_connections
        self._pool: redis.ConnectionPool[Any] | None = None
        self._client: redis.Redis[Any] | None = None

    async def connect(self) -> None:
        """Establish connection to Redis."""
        if self._client is not None:
            return

        self._pool = redis.ConnectionPool.from_url(
            self.redis_url,
            decode_responses=True,
            max_connections=self.max_connections,
        )
        self._client = redis.Redis(connection_pool=self._pool)

        # Test connection
        await self._client.ping()
        logger.info("redis_connected", url=self._mask_url(self.redis_url))

    async def close(self) -> None:
        """Close Redis connection and pool."""
        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
        logger.info("redis_disconnected")

    @property
    def client(self) -> redis.Redis[Any]:
        """Get Redis client.

        Returns:
            Redis client instance

        Raises:
            RuntimeError: If not connected
        """
        if self._client is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._client

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._client is not None

    def _mask_url(self, url: str) -> str:
        """Mask password in URL for logging."""
        if "@" in url:
            parts = url.split("@")
            return f"redis://***@{parts[-1]}"
        return url


# Singleton instance managed via lru_cache
@lru_cache(maxsize=1)
def _create_redis_client() -> RedisClient:
    """Create Redis client instance (cached singleton).

    Returns:
        RedisClient instance
    """
    settings = get_cache_settings()
    return RedisClient(
        redis_url=settings.redis_url,
        max_connections=settings.redis_max_connections,
    )


def get_redis() -> RedisClient:
    """FastAPI dependency for Redis client.

    Returns:
        RedisClient instance
    """
    return _create_redis_client()


async def init_redis() -> RedisClient:
    """Initialize Redis connection (call in lifespan).

    Returns:
        Connected RedisClient
    """
    client = get_redis()
    await client.connect()
    return client


async def close_redis() -> None:
    """Close Redis connection (call in lifespan)."""
    client = _create_redis_client()
    await client.close()
    _create_redis_client.cache_clear()
