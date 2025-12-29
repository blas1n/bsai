"""API test fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from agent.api.auth import get_current_user_id
from agent.api.dependencies import get_db
from agent.cache import SessionCache

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
    ) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> int:
        if key in self._data:
            del self._data[key]
            return 1
        return 0

    async def sadd(self, key: str, *values: str) -> int:
        if key not in self._data:
            self._data[key] = set()
        self._data[key].update(values)
        return len(values)

    async def srem(self, key: str, *values: str) -> int:
        if key not in self._data:
            return 0
        count = 0
        for v in values:
            if v in self._data[key]:
                self._data[key].discard(v)
                count += 1
        return count

    async def smembers(self, key: str) -> set[str]:
        return self._data.get(key, set())

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        pass


@pytest.fixture
def mock_redis() -> MockRedisClient:
    """Create mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def mock_cache(mock_redis: MockRedisClient) -> SessionCache:
    """Create mock session cache."""
    cache = SessionCache.__new__(SessionCache)
    cache._redis = mock_redis
    return cache


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def test_user_id() -> str:
    """Test user ID."""
    return "test-user-123"


@pytest.fixture
def app(
    mock_db: AsyncMock,
    mock_cache: SessionCache,
    test_user_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    from agent.api.config import get_auth_settings
    from agent.api.main import create_app

    # Disable Keycloak auth for tests
    get_auth_settings.cache_clear()
    monkeypatch.setenv("AUTH_AUTH_ENABLED", "false")

    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    async def override_get_current_user_id() -> str:
        return test_user_id

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def mock_session_repo() -> MagicMock:
    """Create mock session repository."""
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.get_by_user_id = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.pause_session = AsyncMock()
    repo.close_session = AsyncMock()
    return repo


@pytest.fixture
def mock_task_repo() -> MagicMock:
    """Create mock task repository."""
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.get_by_session_id = AsyncMock()
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def sample_session_id() -> str:
    """Sample session UUID."""
    return str(uuid4())


@pytest.fixture
def sample_task_id() -> str:
    """Sample task UUID."""
    return str(uuid4())
