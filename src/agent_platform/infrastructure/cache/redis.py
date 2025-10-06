"""
Redis cache client
"""

from typing import Optional
import redis.asyncio as redis
from agent_platform.core.config import settings


class RedisClient:
    """Redis client wrapper"""

    def __init__(self) -> None:
        self.redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Connect to Redis"""
        self.redis = redis.from_url(
            str(settings.REDIS_URL),
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
        )

    async def disconnect(self) -> None:
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()

    async def ping(self) -> bool:
        """Health check"""
        if not self.redis:
            return False
        return await self.redis.ping()

    async def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        return await self.redis.get(key)

    async def set(
        self, key: str, value: str, expire: Optional[int] = None
    ) -> None:
        """Set key-value pair"""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        await self.redis.set(key, value, ex=expire)

    async def delete(self, key: str) -> None:
        """Delete key"""
        if not self.redis:
            raise RuntimeError("Redis not connected")
        await self.redis.delete(key)


# Global instance
redis_client = RedisClient()
