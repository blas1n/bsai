"""Tests for EpisodicMemoryRepository."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from bsai.db.repository.episodic_memory_repo import EpisodicMemoryRepository


class TestEpisodicMemoryRepository:
    """Tests for EpisodicMemoryRepository."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> EpisodicMemoryRepository:
        """Create repository with mock session."""
        return EpisodicMemoryRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_by_user_id_without_memory_types(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting memories without memory_types filter."""
        user_id = "test-user-123"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_user_id(user_id)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_id_with_memory_types(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting memories with memory_types filter (covers line 109)."""
        user_id = "test-user-123"
        memory_types = ["task_outcome", "user_preference"]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_user_id(user_id, memory_types=memory_types)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_id_with_pagination(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting memories with limit and offset."""
        user_id = "test-user-123"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_user_id(user_id, limit=10, offset=5)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_try_lock_for_consolidation_success(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test successful lock acquisition for consolidation (covers lines 302-321)."""
        id1 = uuid4()
        id2 = uuid4()

        mock_memory1 = MagicMock()
        mock_memory1.id = id1
        mock_memory2 = MagicMock()
        mock_memory2.id = id2

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_memory1, mock_memory2]
        mock_session.execute.return_value = mock_result

        result = await repository.try_lock_for_consolidation(id1, id2)

        assert result is not None
        assert result[0].id == id1
        assert result[1].id == id2

    @pytest.mark.asyncio
    async def test_try_lock_for_consolidation_one_locked(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test lock failure when one memory is already locked (covers line 310-312)."""
        id1 = uuid4()
        id2 = uuid4()

        # Only one memory returned (other is locked)
        mock_memory1 = MagicMock()
        mock_memory1.id = id1

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_memory1]
        mock_session.execute.return_value = mock_result

        result = await repository.try_lock_for_consolidation(id1, id2)

        assert result is None

    @pytest.mark.asyncio
    async def test_try_lock_for_consolidation_both_locked(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test lock failure when both memories are locked."""
        id1 = uuid4()
        id2 = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.try_lock_for_consolidation(id1, id2)

        assert result is None

    @pytest.mark.asyncio
    async def test_try_lock_for_consolidation_id_mismatch(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test lock failure when returned IDs don't match (covers lines 315-319)."""
        id1 = uuid4()
        id2 = uuid4()

        # Return two memories but with different IDs
        mock_memory1 = MagicMock()
        mock_memory1.id = uuid4()  # Different from id1
        mock_memory2 = MagicMock()
        mock_memory2.id = uuid4()  # Different from id2

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_memory1, mock_memory2]
        mock_session.execute.return_value = mock_result

        result = await repository.try_lock_for_consolidation(id1, id2)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_stats_by_user(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting user statistics (covers lines 338-360)."""
        user_id = "test-user-123"

        # Mock type query result
        type_row1 = MagicMock()
        type_row1.__getitem__ = lambda self, i: ("task_outcome", 5)[i]
        type_row2 = MagicMock()
        type_row2.__getitem__ = lambda self, i: ("user_preference", 3)[i]

        type_result = MagicMock()
        type_result.all.return_value = [type_row1, type_row2]

        # Mock aggregation query result
        agg_row = MagicMock()
        agg_row.__getitem__ = lambda self, i: (8, 0.75)[i]

        agg_result = MagicMock()
        agg_result.one.return_value = agg_row

        # Configure execute to return different results for different calls
        mock_session.execute.side_effect = [type_result, agg_result]

        result = await repository.get_stats_by_user(user_id)

        assert result["total_memories"] == 8
        assert result["by_type"] == {"task_outcome": 5, "user_preference": 3}
        assert result["average_importance"] == 0.75

    @pytest.mark.asyncio
    async def test_get_stats_by_user_empty(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting user statistics when no memories exist."""
        user_id = "test-user-123"

        # Mock empty type query result
        type_result = MagicMock()
        type_result.all.return_value = []

        # Mock aggregation with None values
        agg_row = MagicMock()
        agg_row.__getitem__ = lambda self, i: (None, None)[i]

        agg_result = MagicMock()
        agg_result.one.return_value = agg_row

        mock_session.execute.side_effect = [type_result, agg_result]

        result = await repository.get_stats_by_user(user_id)

        assert result["total_memories"] == 0
        assert result["by_type"] == {}
        assert result["average_importance"] == 0.0

    @pytest.mark.asyncio
    async def test_get_recent_by_type(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting recent memories by type."""
        user_id = "test-user-123"
        memory_type = "task_outcome"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_recent_by_type(user_id, memory_type)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_access(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test updating access count and timestamp."""
        memory_id = uuid4()

        await repository.update_access(memory_id)

        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_update_importance(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test bulk updating importance scores."""
        memory_ids = [uuid4(), uuid4()]
        decay_factor = 0.95

        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_session.execute.return_value = mock_result

        result = await repository.bulk_update_importance(memory_ids, decay_factor)

        assert result == 2
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_update_importance_empty_list(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test bulk update with empty list returns 0."""
        result = await repository.bulk_update_importance([], 0.95)

        assert result == 0
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_update_importance_no_rowcount(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test bulk update when rowcount is None."""
        memory_ids = [uuid4()]
        decay_factor = 0.95

        mock_result = MagicMock()
        mock_result.rowcount = None
        mock_session.execute.return_value = mock_result

        result = await repository.bulk_update_importance(memory_ids, decay_factor)

        assert result == 0

    @pytest.mark.asyncio
    async def test_count_by_user(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test counting memories by user."""
        user_id = "test-user-123"

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10
        mock_session.execute.return_value = mock_result

        result = await repository.count_by_user(user_id)

        assert result == 10

    @pytest.mark.asyncio
    async def test_count_by_user_none(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test counting memories when result is None."""
        user_id = "test-user-123"

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.count_by_user(user_id)

        assert result == 0

    @pytest.mark.asyncio
    async def test_get_by_session_id(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting memories by session ID."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_session_id(session_id)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_task_id(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting memories by task ID."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_task_id(task_id)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_by_embedding(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test searching memories by embedding vector."""
        user_id = "test-user-123"
        embedding = [0.1] * 1536

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.search_by_embedding(embedding, user_id)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_by_embedding_with_memory_types(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test searching memories by embedding with type filter."""
        user_id = "test-user-123"
        embedding = [0.1] * 1536
        memory_types = ["task_outcome"]

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.search_by_embedding(embedding, user_id, memory_types=memory_types)

        assert result == []

    @pytest.mark.asyncio
    async def test_find_similar_for_consolidation(
        self, repository: EpisodicMemoryRepository, mock_session: AsyncMock
    ) -> None:
        """Test finding similar memory pairs for consolidation."""
        user_id = "test-user-123"

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.find_similar_for_consolidation(user_id)

        assert result == []
        mock_session.execute.assert_called_once()
