"""Tests for SessionCache."""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from bsai.cache.session_cache import SessionCache


class TestSessionCache:
    """Tests for SessionCache class."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock Redis client."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_client.setex = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.sadd = AsyncMock()
        mock_client.srem = AsyncMock()
        mock_client.smembers = AsyncMock(return_value=set())

        redis = MagicMock()
        redis.client = mock_client
        return redis

    @pytest.fixture
    def cache(self, mock_redis_client):
        """Create SessionCache with mock client."""
        return SessionCache(mock_redis_client)

    # Session State Tests

    @pytest.mark.asyncio
    async def test_get_session_state_exists(self, cache, mock_redis_client):
        """Test getting existing session state."""
        session_id = uuid4()
        state_data = {"status": "active", "current_task": "test"}
        mock_redis_client.client.get.return_value = json.dumps(state_data)

        result = await cache.get_session_state(session_id)

        assert result == state_data
        mock_redis_client.client.get.assert_called_once_with(f"session:{session_id}:state")

    @pytest.mark.asyncio
    async def test_get_session_state_not_exists(self, cache, mock_redis_client):
        """Test getting non-existent session state."""
        session_id = uuid4()
        mock_redis_client.client.get.return_value = None

        result = await cache.get_session_state(session_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_set_session_state(self, cache, mock_redis_client):
        """Test setting session state."""
        session_id = uuid4()
        state = {"status": "active", "user_id": "test-user"}

        await cache.set_session_state(session_id, state)

        mock_redis_client.client.setex.assert_called_once()
        call_args = mock_redis_client.client.setex.call_args
        assert call_args[0][0] == f"session:{session_id}:state"
        assert call_args[0][1] == SessionCache.SESSION_STATE_TTL

    @pytest.mark.asyncio
    async def test_set_session_state_custom_ttl(self, cache, mock_redis_client):
        """Test setting session state with custom TTL."""
        session_id = uuid4()
        state = {"status": "active"}
        custom_ttl = 7200

        await cache.set_session_state(session_id, state, ttl=custom_ttl)

        call_args = mock_redis_client.client.setex.call_args
        assert call_args[0][1] == custom_ttl

    @pytest.mark.asyncio
    async def test_invalidate_session_state(self, cache, mock_redis_client):
        """Test invalidating session state."""
        session_id = uuid4()

        await cache.invalidate_session_state(session_id)

        mock_redis_client.client.delete.assert_called_once_with(f"session:{session_id}:state")

    # Context Caching Tests

    @pytest.mark.asyncio
    async def test_cache_context(self, cache, mock_redis_client):
        """Test caching session context."""
        session_id = uuid4()
        context = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]
        summary = "User greeted assistant"
        token_count = 150

        await cache.cache_context(session_id, context, token_count, summary=summary)

        mock_redis_client.client.setex.assert_called_once()
        call_args = mock_redis_client.client.setex.call_args
        assert call_args[0][0] == f"session:{session_id}:context"
        cached_data = json.loads(call_args[0][2])
        assert cached_data["messages"] == context
        assert cached_data["summary"] == summary
        assert cached_data["token_count"] == token_count
        assert "cached_at" in cached_data

    @pytest.mark.asyncio
    async def test_get_cached_context(self, cache, mock_redis_client):
        """Test getting cached context."""
        session_id = uuid4()
        context_data = {
            "messages": [{"role": "user", "content": "Test"}],
            "summary": "Test summary",
            "token_count": 100,
            "cached_at": "2024-01-01T00:00:00",
        }
        mock_redis_client.client.get.return_value = json.dumps(context_data)

        result = await cache.get_cached_context(session_id)

        assert result == context_data
        assert result["token_count"] == 100

    @pytest.mark.asyncio
    async def test_invalidate_context(self, cache, mock_redis_client):
        """Test invalidating cached context."""
        session_id = uuid4()

        await cache.invalidate_context(session_id)

        mock_redis_client.client.delete.assert_called_once_with(f"session:{session_id}:context")

    # Task Progress Tests

    @pytest.mark.asyncio
    async def test_update_task_progress(self, cache, mock_redis_client):
        """Test updating task progress."""
        task_id = uuid4()

        await cache.update_task_progress(
            task_id, current_milestone=2, total_milestones=5, status="in_progress"
        )

        mock_redis_client.client.setex.assert_called_once()
        call_args = mock_redis_client.client.setex.call_args
        assert call_args[0][0] == f"task:{task_id}:progress"
        cached_data = json.loads(call_args[0][2])
        assert cached_data["current"] == 2
        assert cached_data["total"] == 5
        assert cached_data["progress"] == 0.4
        assert cached_data["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_update_task_progress_zero_total(self, cache, mock_redis_client):
        """Test updating progress with zero total milestones."""
        task_id = uuid4()

        await cache.update_task_progress(
            task_id, current_milestone=0, total_milestones=0, status="pending"
        )

        call_args = mock_redis_client.client.setex.call_args
        cached_data = json.loads(call_args[0][2])
        assert cached_data["progress"] == 0.0

    @pytest.mark.asyncio
    async def test_get_task_progress(self, cache, mock_redis_client):
        """Test getting task progress."""
        task_id = uuid4()
        progress_data = {"current": 3, "total": 10, "progress": 0.3, "status": "in_progress"}
        mock_redis_client.client.get.return_value = json.dumps(progress_data)

        result = await cache.get_task_progress(task_id)

        assert result == progress_data

    @pytest.mark.asyncio
    async def test_get_task_progress_not_exists(self, cache, mock_redis_client):
        """Test getting non-existent task progress."""
        task_id = uuid4()
        mock_redis_client.client.get.return_value = None

        result = await cache.get_task_progress(task_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_task_progress(self, cache, mock_redis_client):
        """Test invalidating task progress."""
        task_id = uuid4()

        await cache.invalidate_task_progress(task_id)

        mock_redis_client.client.delete.assert_called_once_with(f"task:{task_id}:progress")

    # User Sessions Tests

    @pytest.mark.asyncio
    async def test_cache_user_sessions(self, cache, mock_redis_client):
        """Test caching user session IDs."""
        user_id = "test-user-123"
        session_ids = [uuid4(), uuid4(), uuid4()]

        await cache.cache_user_sessions(user_id, session_ids)

        mock_redis_client.client.setex.assert_called_once()
        call_args = mock_redis_client.client.setex.call_args
        assert call_args[0][0] == f"user:{user_id}:sessions"

    @pytest.mark.asyncio
    async def test_get_user_sessions(self, cache, mock_redis_client):
        """Test getting cached user sessions."""
        user_id = "test-user-123"
        session_ids = [str(uuid4()), str(uuid4())]
        mock_redis_client.client.get.return_value = json.dumps(session_ids)

        result = await cache.get_user_sessions(user_id)

        assert len(result) == 2
        assert all(isinstance(s, type(uuid4())) for s in result)

    @pytest.mark.asyncio
    async def test_invalidate_user_sessions(self, cache, mock_redis_client):
        """Test invalidating user sessions cache."""
        user_id = "test-user-123"

        await cache.invalidate_user_sessions(user_id)

        mock_redis_client.client.delete.assert_called_once_with(f"user:{user_id}:sessions")

    # WebSocket Connection Tests

    @pytest.mark.asyncio
    async def test_register_ws_connection(self, cache, mock_redis_client):
        """Test registering WebSocket connection."""
        session_id = uuid4()
        connection_id = "conn-123"

        await cache.register_ws_connection(session_id, connection_id)

        mock_redis_client.client.sadd.assert_called_once_with(
            f"ws:connections:{session_id}", connection_id
        )

    @pytest.mark.asyncio
    async def test_unregister_ws_connection(self, cache, mock_redis_client):
        """Test unregistering WebSocket connection."""
        session_id = uuid4()
        connection_id = "conn-123"

        await cache.unregister_ws_connection(session_id, connection_id)

        mock_redis_client.client.srem.assert_called_once_with(
            f"ws:connections:{session_id}", connection_id
        )

    @pytest.mark.asyncio
    async def test_get_ws_connections(self, cache, mock_redis_client):
        """Test getting WebSocket connections."""
        session_id = uuid4()
        connections = {"conn-1", "conn-2", "conn-3"}
        mock_redis_client.client.smembers.return_value = connections

        result = await cache.get_ws_connections(session_id)

        assert result == connections
        mock_redis_client.client.smembers.assert_called_once_with(f"ws:connections:{session_id}")

    @pytest.mark.asyncio
    async def test_clear_ws_connections(self, cache, mock_redis_client):
        """Test clearing WebSocket connections."""
        session_id = uuid4()

        await cache.clear_ws_connections(session_id)

        mock_redis_client.client.delete.assert_called_once_with(f"ws:connections:{session_id}")


class TestSessionCacheTTLConstants:
    """Tests for TTL constants."""

    def test_session_state_ttl(self):
        """Verify session state TTL is 1 hour."""
        assert SessionCache.SESSION_STATE_TTL == 3600

    def test_session_context_ttl(self):
        """Verify session context TTL is 30 minutes."""
        assert SessionCache.SESSION_CONTEXT_TTL == 1800

    def test_task_progress_ttl(self):
        """Verify task progress TTL is 15 minutes."""
        assert SessionCache.TASK_PROGRESS_TTL == 900

    def test_user_sessions_ttl(self):
        """Verify user sessions TTL is 10 minutes."""
        assert SessionCache.USER_SESSIONS_TTL == 600
