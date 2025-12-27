"""Session-specific caching operations.

Provides caching for session state, context, task progress,
and WebSocket connection tracking.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from .redis_client import RedisClient

logger = structlog.get_logger()


class SessionCache:
    """Session-specific caching operations."""

    # TTL constants (in seconds)
    SESSION_STATE_TTL = 3600  # 1 hour
    SESSION_CONTEXT_TTL = 1800  # 30 minutes
    TASK_PROGRESS_TTL = 900  # 15 minutes
    USER_SESSIONS_TTL = 600  # 10 minutes

    def __init__(self, redis_client: RedisClient) -> None:
        """Initialize session cache.

        Args:
            redis_client: Redis client instance
        """
        self._redis = redis_client

    @property
    def client(self) -> Any:
        """Get Redis client."""
        return self._redis.client

    # Session State Methods

    async def get_session_state(self, session_id: UUID) -> dict[str, Any] | None:
        """Get cached session state.

        Args:
            session_id: Session UUID

        Returns:
            Session state dict or None if not cached
        """
        key = f"session:{session_id}:state"
        data = await self.client.get(key)
        if data:
            return json.loads(data)  # type: ignore[no-any-return]
        return None

    async def set_session_state(
        self,
        session_id: UUID,
        state: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """Cache session state.

        Args:
            session_id: Session UUID
            state: Session state dict
            ttl: TTL in seconds (default: SESSION_STATE_TTL)
        """
        key = f"session:{session_id}:state"
        ttl = ttl or self.SESSION_STATE_TTL
        await self.client.setex(key, ttl, json.dumps(state, default=str))
        logger.debug("session_state_cached", session_id=str(session_id), ttl=ttl)

    async def invalidate_session_state(self, session_id: UUID) -> None:
        """Invalidate cached session state.

        Args:
            session_id: Session UUID
        """
        key = f"session:{session_id}:state"
        await self.client.delete(key)
        logger.debug("session_state_invalidated", session_id=str(session_id))

    # Context Caching Methods

    async def cache_context(
        self,
        session_id: UUID,
        context: list[dict[str, str]],
        summary: str | None = None,
        ttl: int | None = None,
    ) -> None:
        """Cache session context for resume operations.

        Args:
            session_id: Session UUID
            context: List of context messages
            summary: Optional context summary
            ttl: TTL in seconds (default: SESSION_CONTEXT_TTL)
        """
        key = f"session:{session_id}:context"
        data = {
            "messages": context,
            "summary": summary,
            "cached_at": datetime.utcnow().isoformat(),
        }
        ttl = ttl or self.SESSION_CONTEXT_TTL
        await self.client.setex(key, ttl, json.dumps(data))
        logger.debug(
            "context_cached",
            session_id=str(session_id),
            message_count=len(context),
            has_summary=summary is not None,
        )

    async def get_cached_context(self, session_id: UUID) -> dict[str, Any] | None:
        """Get cached session context.

        Args:
            session_id: Session UUID

        Returns:
            Context dict with messages and summary, or None
        """
        key = f"session:{session_id}:context"
        data = await self.client.get(key)
        if data:
            return json.loads(data)  # type: ignore[no-any-return]
        return None

    async def invalidate_context(self, session_id: UUID) -> None:
        """Invalidate cached context.

        Args:
            session_id: Session UUID
        """
        key = f"session:{session_id}:context"
        await self.client.delete(key)

    # Task Progress Methods

    async def update_task_progress(
        self,
        task_id: UUID,
        current_milestone: int,
        total_milestones: int,
        status: str,
        ttl: int | None = None,
    ) -> None:
        """Update cached task progress.

        Args:
            task_id: Task UUID
            current_milestone: Current milestone index
            total_milestones: Total number of milestones
            status: Task status
            ttl: TTL in seconds (default: TASK_PROGRESS_TTL)
        """
        key = f"task:{task_id}:progress"
        progress = current_milestone / total_milestones if total_milestones > 0 else 0.0
        data = {
            "current": current_milestone,
            "total": total_milestones,
            "progress": progress,
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        ttl = ttl or self.TASK_PROGRESS_TTL
        await self.client.setex(key, ttl, json.dumps(data))

    async def get_task_progress(self, task_id: UUID) -> dict[str, Any] | None:
        """Get cached task progress.

        Args:
            task_id: Task UUID

        Returns:
            Progress dict or None
        """
        key = f"task:{task_id}:progress"
        data = await self.client.get(key)
        if data:
            return json.loads(data)  # type: ignore[no-any-return]
        return None

    async def invalidate_task_progress(self, task_id: UUID) -> None:
        """Invalidate cached task progress.

        Args:
            task_id: Task UUID
        """
        key = f"task:{task_id}:progress"
        await self.client.delete(key)

    # User Sessions Methods

    async def cache_user_sessions(
        self,
        user_id: str,
        session_ids: list[UUID],
        ttl: int | None = None,
    ) -> None:
        """Cache user's session IDs.

        Args:
            user_id: User ID
            session_ids: List of session UUIDs
            ttl: TTL in seconds (default: USER_SESSIONS_TTL)
        """
        key = f"user:{user_id}:sessions"
        ttl = ttl or self.USER_SESSIONS_TTL
        await self.client.setex(key, ttl, json.dumps([str(s) for s in session_ids]))

    async def get_user_sessions(self, user_id: str) -> list[UUID] | None:
        """Get cached user session IDs.

        Args:
            user_id: User ID

        Returns:
            List of session UUIDs or None
        """
        key = f"user:{user_id}:sessions"
        data = await self.client.get(key)
        if data:
            return [UUID(s) for s in json.loads(data)]
        return None

    async def invalidate_user_sessions(self, user_id: str) -> None:
        """Invalidate cached user sessions.

        Args:
            user_id: User ID
        """
        key = f"user:{user_id}:sessions"
        await self.client.delete(key)

    # WebSocket Connection Tracking

    async def register_ws_connection(
        self,
        session_id: UUID,
        connection_id: str,
    ) -> None:
        """Register WebSocket connection.

        Args:
            session_id: Session UUID
            connection_id: Unique connection identifier
        """
        key = f"ws:connections:{session_id}"
        await self.client.sadd(key, connection_id)
        logger.debug(
            "ws_connection_registered",
            session_id=str(session_id),
            connection_id=connection_id,
        )

    async def unregister_ws_connection(
        self,
        session_id: UUID,
        connection_id: str,
    ) -> None:
        """Unregister WebSocket connection.

        Args:
            session_id: Session UUID
            connection_id: Unique connection identifier
        """
        key = f"ws:connections:{session_id}"
        await self.client.srem(key, connection_id)
        logger.debug(
            "ws_connection_unregistered",
            session_id=str(session_id),
            connection_id=connection_id,
        )

    async def get_ws_connections(self, session_id: UUID) -> set[str]:
        """Get WebSocket connections for session.

        Args:
            session_id: Session UUID

        Returns:
            Set of connection IDs
        """
        key = f"ws:connections:{session_id}"
        return await self.client.smembers(key)  # type: ignore[no-any-return]

    async def clear_ws_connections(self, session_id: UUID) -> None:
        """Clear all WebSocket connections for session.

        Args:
            session_id: Session UUID
        """
        key = f"ws:connections:{session_id}"
        await self.client.delete(key)
