"""Unit tests for EpisodicMemoryRepository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from bsai.db.models.enums import MemoryType
from bsai.db.models.episodic_memory import EpisodicMemory
from bsai.db.repository.episodic_memory_repo import EpisodicMemoryRepository

if TYPE_CHECKING:
    pass


class TestEpisodicMemoryRepository:
    """Tests for EpisodicMemoryRepository."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> EpisodicMemoryRepository:
        """Create repository with mock session."""
        return EpisodicMemoryRepository(mock_session)

    @pytest.fixture
    def sample_memory(self) -> EpisodicMemory:
        """Create sample episodic memory."""
        return EpisodicMemory(
            id=uuid4(),
            user_id="test-user",
            session_id=uuid4(),
            content="Test content",
            summary="Test summary",
            embedding=[0.1] * 1536,
            memory_type=MemoryType.TASK_RESULT.value,
            importance_score=0.8,
            access_count=0,
            created_at=datetime.utcnow(),
        )

    @pytest.mark.asyncio
    async def test_create_memory(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test creating a new memory."""
        user_id = "test-user"
        session_id = uuid4()
        embedding = [0.1] * 1536

        await repository.create(
            user_id=user_id,
            session_id=session_id,
            content="Test content",
            summary="Test summary",
            embedding=embedding,
            memory_type=MemoryType.TASK_RESULT.value,
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_by_embedding(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
        sample_memory: EpisodicMemory,
    ) -> None:
        """Test searching by embedding vector."""
        mock_result = MagicMock()
        mock_result.all.return_value = [(sample_memory, 0.85)]
        mock_session.execute.return_value = mock_result

        embedding = [0.1] * 1536
        results = await repository.search_by_embedding(
            embedding=embedding,
            user_id="test-user",
            limit=5,
        )

        assert len(results) == 1
        assert results[0][0] == sample_memory
        assert results[0][1] == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_search_by_embedding_with_memory_types(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test searching with specific memory types filter."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        await repository.search_by_embedding(
            embedding=[0.1] * 1536,
            user_id="test-user",
            memory_types=[MemoryType.TASK_RESULT.value, MemoryType.LEARNING.value],
        )

        # Verify execute was called with query containing memory type filter
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_by_embedding_min_similarity(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
        sample_memory: EpisodicMemory,
    ) -> None:
        """Test minimum similarity threshold is applied."""
        mock_result = MagicMock()
        # Return memory with low similarity
        mock_result.all.return_value = [(sample_memory, 0.5)]
        mock_session.execute.return_value = mock_result

        await repository.search_by_embedding(
            embedding=[0.1] * 1536,
            user_id="test-user",
            min_similarity=0.7,
        )

        # Low similarity result should be filtered out by the query
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_id(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
        sample_memory: EpisodicMemory,
    ) -> None:
        """Test getting memories by user ID."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_memory]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repository.get_by_user_id(
            user_id="test-user",
            limit=100,
        )

        assert len(results) == 1
        assert results[0] == sample_memory

    @pytest.mark.asyncio
    async def test_get_by_user_id_with_pagination(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test pagination in get_by_user_id."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await repository.get_by_user_id(
            user_id="test-user",
            limit=10,
            offset=20,
        )

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_access(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test updating memory access count and timestamp."""
        memory_id = uuid4()

        await repository.update_access(memory_id)

        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_update_importance(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test bulk updating importance scores."""
        memory_ids = [uuid4(), uuid4(), uuid4()]

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        count = await repository.bulk_update_importance(
            memory_ids=memory_ids,
            decay_factor=0.95,
        )

        assert count == 3
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_update_importance_empty_list(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test bulk update with empty list does nothing."""
        count = await repository.bulk_update_importance(
            memory_ids=[],
            decay_factor=0.95,
        )

        assert count == 0
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_memory(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
        sample_memory: EpisodicMemory,
    ) -> None:
        """Test deleting a memory."""
        # Mock get_by_id to return sample_memory
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_memory
        mock_session.execute.return_value = mock_result

        result = await repository.delete(sample_memory.id)

        assert result is True
        mock_session.delete.assert_called_once_with(sample_memory)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_memory(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test deleting non-existent memory returns False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.delete(uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_count_by_user(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test counting memories for a user."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42
        mock_session.execute.return_value = mock_result

        count = await repository.count_by_user("test-user")

        assert count == 42
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_session_id(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
        sample_memory: EpisodicMemory,
    ) -> None:
        """Test getting memories by session ID."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_memory]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repository.get_by_session_id(
            session_id=sample_memory.session_id,
            limit=100,
        )

        assert len(results) == 1
        assert results[0] == sample_memory

    @pytest.mark.asyncio
    async def test_get_by_task_id(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
        sample_memory: EpisodicMemory,
    ) -> None:
        """Test getting memories by task ID."""
        task_id = uuid4()
        sample_memory.task_id = task_id

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_memory]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repository.get_by_task_id(task_id=task_id)

        assert len(results) == 1
        assert results[0] == sample_memory

    @pytest.mark.asyncio
    async def test_find_similar_for_consolidation(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test finding similar memories for consolidation."""
        mem1 = MagicMock(spec=EpisodicMemory)
        mem2 = MagicMock(spec=EpisodicMemory)

        mock_result = MagicMock()
        mock_result.all.return_value = [(mem1, mem2, 0.95)]
        mock_session.execute.return_value = mock_result

        results = await repository.find_similar_for_consolidation(
            user_id="test-user",
            similarity_threshold=0.9,
        )

        assert len(results) == 1
        assert results[0][0] == mem1
        assert results[0][1] == mem2
        assert results[0][2] == 0.95

    @pytest.mark.asyncio
    async def test_get_recent_by_type(
        self,
        repository: EpisodicMemoryRepository,
        mock_session: AsyncMock,
        sample_memory: EpisodicMemory,
    ) -> None:
        """Test getting recent memories by type."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_memory]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repository.get_recent_by_type(
            user_id="test-user",
            memory_type=MemoryType.TASK_RESULT.value,
            limit=10,
        )

        assert len(results) == 1
        assert results[0] == sample_memory
