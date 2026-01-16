"""API tests for memories router."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.auth import get_current_user_id
from agent.api.dependencies import get_cache, get_db
from agent.db.models.enums import MemoryType
from agent.db.models.episodic_memory import EpisodicMemory

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create mock cache."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def test_user_id() -> str:
    """Test user ID."""
    return "test-user-123"


@pytest.fixture
def sample_memory_id() -> str:
    """Sample memory UUID."""
    return str(uuid4())


@pytest.fixture
def sample_session_id() -> str:
    """Sample session UUID."""
    return str(uuid4())


@pytest.fixture
def sample_memory(sample_memory_id: str, sample_session_id: str, test_user_id: str) -> MagicMock:
    """Create sample memory object."""
    memory = MagicMock(spec=EpisodicMemory)
    memory.id = sample_memory_id
    memory.user_id = test_user_id
    memory.session_id = sample_session_id
    memory.task_id = None
    memory.content = "Test memory content"
    memory.summary = "Test summary"
    memory.memory_type = MemoryType.TASK_RESULT.value
    memory.importance_score = 0.8
    memory.access_count = 5
    memory.tags = ["test", "sample"]
    memory.metadata_json = {"key": "value"}
    memory.created_at = datetime.utcnow()
    memory.last_accessed_at = datetime.utcnow()
    return memory


@pytest.fixture
def app(
    mock_db: AsyncMock,
    mock_cache: MagicMock,
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

    async def override_get_cache() -> MagicMock:
        return mock_cache

    async def override_get_current_user_id() -> str:
        return test_user_id

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_cache] = override_get_cache
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestMemoriesSearch:
    """Tests for POST /memories/search endpoint."""

    def test_search_memories_success(
        self,
        client: TestClient,
        sample_memory: MagicMock,
    ) -> None:
        """Test successful memory search."""
        with patch("agent.api.routers.memories.LongTermMemoryManager") as mock_manager_class:
            mock_manager = MagicMock()
            # Return list of tuples (memory, score) like the real implementation
            mock_manager.search_similar = AsyncMock(return_value=[(sample_memory, 0.85)])
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/v1/memories/search",
                json={"query": "test query", "limit": 5},
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["similarity"] == 0.85
            assert data[0]["memory"]["summary"] == sample_memory.summary

    def test_search_memories_empty_query(self, client: TestClient) -> None:
        """Test search with empty query."""
        response = client.post(
            "/api/v1/memories/search",
            json={"query": "", "limit": 5},
        )

        assert response.status_code == 422

    def test_search_memories_with_memory_types(
        self,
        client: TestClient,
    ) -> None:
        """Test search with memory type filter."""
        with patch("agent.api.routers.memories.LongTermMemoryManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.search_similar = AsyncMock(return_value=[])
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/v1/memories/search",
                json={
                    "query": "test",
                    "memory_types": ["task_result", "learning"],
                },
            )

            assert response.status_code == 200
            mock_manager.search_similar.assert_called_once()


class TestMemoriesList:
    """Tests for GET /memories endpoint."""

    def test_list_memories_success(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        sample_memory: MagicMock,
        test_user_id: str,
    ) -> None:
        """Test listing memories."""
        with patch("agent.api.routers.memories.EpisodicMemoryRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_user_id = AsyncMock(return_value=[sample_memory])
            mock_repo.count_by_user = AsyncMock(return_value=1)
            mock_repo_class.return_value = mock_repo

            response = client.get("/api/v1/memories")

            assert response.status_code == 200
            data = response.json()
            # Response is PaginatedResponse
            assert "items" in data
            assert len(data["items"]) == 1
            assert data["items"][0]["summary"] == sample_memory.summary
            assert data["total"] == 1

    def test_list_memories_with_pagination(
        self,
        client: TestClient,
    ) -> None:
        """Test listing memories with pagination."""
        with patch("agent.api.routers.memories.EpisodicMemoryRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_user_id = AsyncMock(return_value=[])
            mock_repo.count_by_user = AsyncMock(return_value=0)
            mock_repo_class.return_value = mock_repo

            response = client.get("/api/v1/memories?limit=10&offset=20")

            assert response.status_code == 200
            mock_repo.get_by_user_id.assert_called_once()
            call_kwargs = mock_repo.get_by_user_id.call_args[1]
            assert call_kwargs["limit"] == 10
            assert call_kwargs["offset"] == 20

    def test_list_memories_with_type_filter(
        self,
        client: TestClient,
    ) -> None:
        """Test listing memories with type filter."""
        with patch("agent.api.routers.memories.EpisodicMemoryRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_user_id = AsyncMock(return_value=[])
            mock_repo.count_by_user = AsyncMock(return_value=0)
            mock_repo_class.return_value = mock_repo

            response = client.get("/api/v1/memories?memory_type=task_result")

            assert response.status_code == 200


class TestMemoriesGet:
    """Tests for GET /memories/{memory_id} endpoint."""

    def test_get_memory_success(
        self,
        client: TestClient,
        sample_memory: MagicMock,
        sample_memory_id: str,
    ) -> None:
        """Test getting single memory."""
        with patch("agent.api.routers.memories.EpisodicMemoryRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=sample_memory)
            mock_repo_class.return_value = mock_repo

            response = client.get(f"/api/v1/memories/{sample_memory_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["content"] == sample_memory.content

    def test_get_memory_not_found(
        self,
        client: TestClient,
    ) -> None:
        """Test getting non-existent memory."""
        with patch("agent.api.routers.memories.EpisodicMemoryRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            response = client.get(f"/api/v1/memories/{uuid4()}")

            assert response.status_code == 404

    def test_get_memory_wrong_user(
        self,
        client: TestClient,
        sample_memory: MagicMock,
        sample_memory_id: str,
    ) -> None:
        """Test getting memory belonging to different user."""
        sample_memory.user_id = "different-user"

        with patch("agent.api.routers.memories.EpisodicMemoryRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=sample_memory)
            mock_repo_class.return_value = mock_repo

            response = client.get(f"/api/v1/memories/{sample_memory_id}")

            assert response.status_code == 404


class TestMemoriesDelete:
    """Tests for DELETE /memories/{memory_id} endpoint."""

    def test_delete_memory_success(
        self,
        client: TestClient,
        sample_memory: MagicMock,
        sample_memory_id: str,
    ) -> None:
        """Test deleting memory."""
        with patch("agent.api.routers.memories.EpisodicMemoryRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=sample_memory)
            mock_repo.delete = AsyncMock(return_value=True)
            mock_repo_class.return_value = mock_repo

            response = client.delete(f"/api/v1/memories/{sample_memory_id}")

            assert response.status_code == 204

    def test_delete_memory_not_found(
        self,
        client: TestClient,
    ) -> None:
        """Test deleting non-existent memory."""
        with patch("agent.api.routers.memories.EpisodicMemoryRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            response = client.delete(f"/api/v1/memories/{uuid4()}")

            assert response.status_code == 404


class TestMemoriesStats:
    """Tests for GET /memories/stats endpoint."""

    def test_get_stats_success(
        self,
        client: TestClient,
        mock_db: AsyncMock,
    ) -> None:
        """Test getting memory statistics."""
        with patch("agent.api.routers.memories.LongTermMemoryManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_memory_stats = AsyncMock(
                return_value={
                    "total_memories": 42,
                    "by_type": {"task_result": 20, "learning": 22},
                    "average_importance": 0.75,
                }
            )
            mock_manager_class.return_value = mock_manager

            response = client.get("/api/v1/memories/stats")

            assert response.status_code == 200
            data = response.json()
            assert "total_memories" in data
            assert data["total_memories"] == 42
            assert data["average_importance"] == 0.75


class TestMemoriesConsolidate:
    """Tests for POST /memories/consolidate endpoint."""

    def test_consolidate_success(
        self,
        client: TestClient,
    ) -> None:
        """Test consolidating similar memories."""
        with (
            patch("agent.api.routers.memories.LongTermMemoryManager") as mock_manager_class,
            patch("agent.api.routers.memories.EpisodicMemoryRepository") as mock_repo_class,
        ):
            mock_manager = MagicMock()
            mock_manager.consolidate_memories = AsyncMock(return_value=5)
            mock_manager_class.return_value = mock_manager

            mock_repo = MagicMock()
            mock_repo.count_by_user = AsyncMock(return_value=10)
            mock_repo_class.return_value = mock_repo

            response = client.post("/api/v1/memories/consolidate")

            assert response.status_code == 200
            data = response.json()
            assert data["consolidated_count"] == 5
            assert data["remaining_count"] == 10


class TestMemoriesDecay:
    """Tests for POST /memories/decay endpoint."""

    def test_decay_success(
        self,
        client: TestClient,
    ) -> None:
        """Test applying importance decay."""
        with patch("agent.api.routers.memories.LongTermMemoryManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.decay_memories = AsyncMock(return_value=10)
            mock_manager_class.return_value = mock_manager

            response = client.post("/api/v1/memories/decay")

            assert response.status_code == 200
            data = response.json()
            assert data["decayed_count"] == 10
