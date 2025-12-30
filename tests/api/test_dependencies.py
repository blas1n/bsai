"""Dependency injection tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.api.dependencies import get_cache, get_db

if TYPE_CHECKING:
    pass


class TestGetDB:
    """Tests for get_db dependency."""

    @pytest.mark.asyncio
    async def test_yields_database_session(self) -> None:
        """get_db yields a database session."""
        mock_session = AsyncMock()

        with patch(
            "agent.api.dependencies.get_db_session",
        ) as mock_get_session:
            # Mock the async generator
            async def mock_generator() -> AsyncGenerator[Any, None]:
                yield mock_session

            mock_get_session.return_value = mock_generator()

            # Call get_db
            result = None
            async for session in get_db():
                result = session
                break

            assert result is mock_session

    @pytest.mark.asyncio
    async def test_session_generator_pattern(self) -> None:
        """get_db follows generator pattern for proper cleanup."""
        mock_session = AsyncMock()

        with patch(
            "agent.api.dependencies.get_db_session",
        ) as mock_get_session:

            async def mock_generator() -> AsyncGenerator[Any, None]:
                yield mock_session

            mock_get_session.return_value = mock_generator()

            # Exhaust the generator
            sessions = []
            async for session in get_db():
                sessions.append(session)

            assert len(sessions) == 1


class TestGetCache:
    """Tests for get_cache dependency."""

    def test_returns_session_cache(self) -> None:
        """get_cache returns SessionCache instance."""
        mock_redis = MagicMock()

        with patch("agent.api.dependencies.SessionCache") as mock_cache_class:
            mock_cache_instance = MagicMock()
            mock_cache_class.return_value = mock_cache_instance

            result = get_cache(mock_redis)

            mock_cache_class.assert_called_once_with(mock_redis)
            assert result is mock_cache_instance

    def test_uses_provided_redis_client(self) -> None:
        """get_cache uses the provided Redis client."""
        mock_redis = MagicMock()
        mock_redis.client = "test-client"

        with patch("agent.api.dependencies.SessionCache") as mock_cache_class:
            get_cache(mock_redis)

            # Verify Redis client was passed
            mock_cache_class.assert_called_once_with(mock_redis)


class TestTypeAliases:
    """Tests for dependency type aliases."""

    def test_db_session_type_alias_exists(self) -> None:
        """DBSession type alias is defined."""
        from agent.api.dependencies import DBSession

        # Should not raise
        assert DBSession is not None

    def test_cache_type_alias_exists(self) -> None:
        """Cache type alias is defined."""
        from agent.api.dependencies import Cache

        # Should not raise
        assert Cache is not None

    def test_current_user_id_type_alias_exists(self) -> None:
        """CurrentUserId type alias is defined."""
        from agent.api.dependencies import CurrentUserId

        # Should not raise
        assert CurrentUserId is not None
