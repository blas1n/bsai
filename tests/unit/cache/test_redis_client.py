"""Redis client tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bsai.cache.redis_client import (
    RedisClient,
    _create_redis_client,
    close_redis,
    get_redis,
    init_redis,
)

if TYPE_CHECKING:
    pass


class TestRedisClient:
    """Tests for RedisClient class."""

    def test_init_stores_config(self) -> None:
        """Init stores redis URL and max connections."""
        client = RedisClient("redis://localhost:6379/0", max_connections=50)

        assert client.redis_url == "redis://localhost:6379/0"
        assert client.max_connections == 50
        assert client._client is None
        assert client._pool is None

    @pytest.mark.asyncio
    async def test_connect_creates_pool_and_client(self) -> None:
        """Connect creates connection pool and client."""
        client = RedisClient("redis://localhost:6379/0")

        with (
            patch("bsai.cache.redis_client.redis.ConnectionPool") as mock_pool_class,
            patch("bsai.cache.redis_client.redis.Redis") as mock_redis_class,
        ):
            mock_pool = MagicMock()
            mock_pool_class.from_url.return_value = mock_pool

            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis_class.return_value = mock_redis

            await client.connect()

            mock_pool_class.from_url.assert_called_once()
            mock_redis_class.assert_called_once_with(connection_pool=mock_pool)
            mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_skips_if_already_connected(self) -> None:
        """Connect does nothing if already connected."""
        client = RedisClient("redis://localhost:6379/0")
        client._client = MagicMock()

        with patch("bsai.cache.redis_client.redis.ConnectionPool") as mock_pool:
            await client.connect()
            mock_pool.from_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_disconnects(self) -> None:
        """Close closes client and pool."""
        client = RedisClient("redis://localhost:6379/0")
        mock_client = AsyncMock()
        mock_pool = AsyncMock()
        client._client = mock_client
        client._pool = mock_pool

        await client.close()

        mock_client.close.assert_called_once()
        mock_pool.disconnect.assert_called_once()
        assert client._client is None
        assert client._pool is None

    @pytest.mark.asyncio
    async def test_close_handles_none_client(self) -> None:
        """Close handles None client gracefully."""
        client = RedisClient("redis://localhost:6379/0")

        await client.close()

        assert client._client is None

    def test_client_property_returns_client(self) -> None:
        """Client property returns Redis client."""
        client = RedisClient("redis://localhost:6379/0")
        mock_redis = MagicMock()
        client._client = mock_redis

        result = client.client

        assert result is mock_redis

    def test_client_property_raises_when_not_connected(self) -> None:
        """Client property raises RuntimeError when not connected."""
        client = RedisClient("redis://localhost:6379/0")

        with pytest.raises(RuntimeError, match="Redis not connected"):
            _ = client.client

    def test_is_connected_true_when_connected(self) -> None:
        """is_connected returns True when client exists."""
        client = RedisClient("redis://localhost:6379/0")
        client._client = MagicMock()

        assert client.is_connected is True

    def test_is_connected_false_when_not_connected(self) -> None:
        """is_connected returns False when client is None."""
        client = RedisClient("redis://localhost:6379/0")

        assert client.is_connected is False

    def test_mask_url_hides_password(self) -> None:
        """_mask_url hides password in URL."""
        client = RedisClient("redis://localhost:6379/0")

        result = client._mask_url("redis://user:password@localhost:6379/0")

        assert result == "redis://***@localhost:6379/0"
        assert "password" not in result

    def test_mask_url_handles_no_password(self) -> None:
        """_mask_url handles URL without password."""
        client = RedisClient("redis://localhost:6379/0")

        result = client._mask_url("redis://localhost:6379/0")

        assert result == "redis://localhost:6379/0"


class TestCreateRedisClient:
    """Tests for _create_redis_client function."""

    def test_creates_client_with_settings(self) -> None:
        """Creates client with settings from config."""
        _create_redis_client.cache_clear()

        with patch("bsai.cache.redis_client.get_cache_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                redis_url="redis://test:6379/1",
                redis_max_connections=30,
            )

            client = _create_redis_client()

            assert client.redis_url == "redis://test:6379/1"
            assert client.max_connections == 30

        _create_redis_client.cache_clear()

    def test_caches_client_instance(self) -> None:
        """Caches and returns same client instance."""
        _create_redis_client.cache_clear()

        with patch("bsai.cache.redis_client.get_cache_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                redis_url="redis://localhost:6379/0",
                redis_max_connections=20,
            )

            client1 = _create_redis_client()
            client2 = _create_redis_client()

            assert client1 is client2

        _create_redis_client.cache_clear()


class TestGetRedis:
    """Tests for get_redis function."""

    def test_returns_redis_client(self) -> None:
        """Returns RedisClient instance."""
        _create_redis_client.cache_clear()

        with patch("bsai.cache.redis_client.get_cache_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                redis_url="redis://localhost:6379/0",
                redis_max_connections=20,
            )

            result = get_redis()

            assert isinstance(result, RedisClient)

        _create_redis_client.cache_clear()


class TestInitRedis:
    """Tests for init_redis function."""

    @pytest.mark.asyncio
    async def test_connects_and_returns_client(self) -> None:
        """Initializes and returns connected client."""
        _create_redis_client.cache_clear()

        with (
            patch("bsai.cache.redis_client.get_cache_settings") as mock_settings,
            patch.object(RedisClient, "connect", new_callable=AsyncMock) as mock_connect,
        ):
            mock_settings.return_value = MagicMock(
                redis_url="redis://localhost:6379/0",
                redis_max_connections=20,
            )

            result = await init_redis()

            mock_connect.assert_called_once()
            assert isinstance(result, RedisClient)

        _create_redis_client.cache_clear()


class TestCloseRedis:
    """Tests for close_redis function."""

    @pytest.mark.asyncio
    async def test_closes_client_and_clears_cache(self) -> None:
        """Closes client and clears singleton cache."""
        _create_redis_client.cache_clear()

        with (
            patch("bsai.cache.redis_client.get_cache_settings") as mock_settings,
            patch.object(RedisClient, "close", new_callable=AsyncMock) as mock_close,
        ):
            mock_settings.return_value = MagicMock(
                redis_url="redis://localhost:6379/0",
                redis_max_connections=20,
            )

            # First, ensure client is cached
            _ = _create_redis_client()

            await close_redis()

            mock_close.assert_called_once()
            # Cache should be cleared (next call creates new instance)

        _create_redis_client.cache_clear()
