"""Unit tests for LongTermMemoryManager."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.models.enums import MemoryType
from agent.memory.manager import LongTermMemoryManager

if TYPE_CHECKING:
    pass


class TestLongTermMemoryManager:
    """Tests for LongTermMemoryManager."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def mock_embedding_service(self) -> MagicMock:
        """Create mock embedding service."""
        service = MagicMock()
        service.embed_with_cache = AsyncMock(return_value=[0.1] * 1536)
        service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        return service

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock episodic memory repository."""
        repo = MagicMock()
        repo.create = AsyncMock()
        repo.search_by_embedding = AsyncMock(return_value=[])
        repo.get_by_user_id = AsyncMock(return_value=[])
        repo.update_access = AsyncMock()
        repo.bulk_update_importance = AsyncMock(return_value=0)
        repo.find_similar_for_consolidation = AsyncMock(return_value=[])
        repo.delete = AsyncMock(return_value=True)
        repo.update = AsyncMock()
        return repo

    @pytest.fixture
    def manager(
        self,
        mock_session: AsyncMock,
        mock_embedding_service: MagicMock,
        mock_repository: MagicMock,
    ) -> LongTermMemoryManager:
        """Create LongTermMemoryManager with mocks."""
        mgr = LongTermMemoryManager(mock_session, mock_embedding_service)
        mgr._repo = mock_repository
        return mgr

    @pytest.mark.asyncio
    async def test_store_memory_success(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test storing a memory successfully."""
        user_id = "test-user"
        session_id = uuid4()
        content = "Test memory content"

        mock_memory = MagicMock()
        mock_memory.id = uuid4()
        mock_repository.create.return_value = mock_memory

        result = await manager.store_memory(
            user_id=user_id,
            session_id=session_id,
            content=content,
            memory_type=MemoryType.TASK_RESULT,
        )

        assert result == mock_memory
        mock_embedding_service.embed_with_cache.assert_called_once()
        mock_repository.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_memory_long_content_truncates_summary(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test storing memory with long content truncates summary."""
        mock_memory = MagicMock()
        mock_repository.create.return_value = mock_memory

        long_content = "x" * 3000  # Exceeds MAX_CONTENT_LENGTH

        await manager.store_memory(
            user_id="test-user",
            session_id=uuid4(),
            content=long_content,
            memory_type=MemoryType.LEARNING,
        )

        call_kwargs = mock_repository.create.call_args[1]
        assert len(call_kwargs["summary"]) < len(long_content)
        assert call_kwargs["summary"].endswith("...")

    @pytest.mark.asyncio
    async def test_store_task_result(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test storing task result creates properly formatted memory."""
        mock_memory = MagicMock()
        mock_repository.create.return_value = mock_memory

        await manager.store_task_result(
            user_id="test-user",
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Build a feature",
            final_result="Feature built successfully",
            milestones_summary="Step 1: Done, Step 2: Done",
        )

        call_kwargs = mock_repository.create.call_args[1]
        assert call_kwargs["memory_type"] == MemoryType.TASK_RESULT.value
        assert "Build a feature" in call_kwargs["content"]
        assert "Feature built successfully" in call_kwargs["content"]
        assert call_kwargs["importance_score"] == 0.7

    @pytest.mark.asyncio
    async def test_store_qa_learning(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test storing QA learning creates properly formatted memory."""
        mock_memory = MagicMock()
        mock_repository.create.return_value = mock_memory

        await manager.store_qa_learning(
            user_id="test-user",
            session_id=uuid4(),
            original_output="Initial output",
            qa_feedback="Needs improvement",
            improved_output="Better output",
        )

        call_kwargs = mock_repository.create.call_args[1]
        assert call_kwargs["memory_type"] == MemoryType.LEARNING.value
        assert "QA Learning" in call_kwargs["content"]
        assert call_kwargs["importance_score"] == 0.8

    @pytest.mark.asyncio
    async def test_store_error(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test storing error creates properly formatted memory."""
        mock_memory = MagicMock()
        mock_repository.create.return_value = mock_memory

        await manager.store_error(
            user_id="test-user",
            session_id=uuid4(),
            error_message="Connection timeout",
            context="While calling external API",
        )

        call_kwargs = mock_repository.create.call_args[1]
        assert call_kwargs["memory_type"] == MemoryType.ERROR.value
        assert "Connection timeout" in call_kwargs["content"]
        assert "error" in call_kwargs["tags"]

    @pytest.mark.asyncio
    async def test_search_similar(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test searching similar memories."""
        mock_memory = MagicMock()
        mock_memory.id = uuid4()
        mock_memory.summary = "Test memory"
        mock_memory.last_accessed_at = None
        mock_repository.search_by_embedding.return_value = [(mock_memory, 0.9)]

        results = await manager.search_similar(
            user_id="test-user",
            query="search query",
            limit=5,
        )

        assert len(results) == 1
        assert results[0][0] == mock_memory
        assert results[0][1] == 0.9
        mock_embedding_service.embed_with_cache.assert_called_once_with("search query")
        mock_repository.update_access.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_similar_with_memory_types(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test searching with specific memory types."""
        mock_repository.search_by_embedding.return_value = []

        await manager.search_similar(
            user_id="test-user",
            query="query",
            memory_types=[MemoryType.TASK_RESULT, MemoryType.LEARNING],
        )

        call_kwargs = mock_repository.search_by_embedding.call_args[1]
        assert MemoryType.TASK_RESULT.value in call_kwargs["memory_types"]
        assert MemoryType.LEARNING.value in call_kwargs["memory_types"]

    @pytest.mark.asyncio
    async def test_get_relevant_context(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting relevant context for a task."""
        mock_memory = MagicMock()
        mock_memory.id = uuid4()
        mock_memory.summary = "Previous task result"
        mock_memory.content = "Full content"
        mock_memory.memory_type = MemoryType.TASK_RESULT.value
        mock_memory.importance_score = 0.8
        mock_memory.last_accessed_at = None
        mock_repository.search_by_embedding.return_value = [(mock_memory, 0.85)]

        context = await manager.get_relevant_context(
            user_id="test-user",
            current_task="New task description",
        )

        assert "Previous task result" in context
        assert "0.85" in context  # similarity score

    @pytest.mark.asyncio
    async def test_get_relevant_context_no_memories(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting context when no relevant memories exist."""
        mock_repository.search_by_embedding.return_value = []

        context = await manager.get_relevant_context(
            user_id="test-user",
            current_task="New task",
        )

        assert context == ""

    @pytest.mark.asyncio
    async def test_decay_memories(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test decaying memory importance scores."""
        mock_memory1 = MagicMock()
        mock_memory1.id = uuid4()
        mock_memory1.importance_score = 0.8
        mock_memory2 = MagicMock()
        mock_memory2.id = uuid4()
        mock_memory2.importance_score = 0.6
        mock_repository.get_by_user_id.return_value = [mock_memory1, mock_memory2]
        mock_repository.bulk_update_importance.return_value = 2

        result = await manager.decay_memories(user_id="test-user", decay_factor=0.95)

        assert result == 2
        mock_repository.bulk_update_importance.assert_called_once()

    @pytest.mark.asyncio
    async def test_decay_memories_skips_low_importance(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test decay skips memories below minimum importance."""
        mock_memory = MagicMock()
        mock_memory.id = uuid4()
        mock_memory.importance_score = 0.05  # Below default min_importance
        mock_repository.get_by_user_id.return_value = [mock_memory]

        result = await manager.decay_memories(user_id="test-user")

        assert result == 0
        mock_repository.bulk_update_importance.assert_not_called()

    @pytest.mark.asyncio
    async def test_consolidate_memories(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test consolidating similar memories."""
        mem1 = MagicMock()
        mem1.id = uuid4()
        mem1.importance_score = 0.8

        mem2 = MagicMock()
        mem2.id = uuid4()
        mem2.importance_score = 0.6

        mock_repository.find_similar_for_consolidation.return_value = [(mem1, mem2, 0.92)]

        result = await manager.consolidate_memories(
            user_id="test-user",
            similarity_threshold=0.9,
        )

        assert result == 1
        mock_repository.delete.assert_called_once_with(mem2.id)
        mock_repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_consolidate_keeps_higher_importance(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test consolidation keeps the memory with higher importance."""
        mem1 = MagicMock()
        mem1.id = uuid4()
        mem1.importance_score = 0.5

        mem2 = MagicMock()
        mem2.id = uuid4()
        mem2.importance_score = 0.9  # Higher importance

        mock_repository.find_similar_for_consolidation.return_value = [(mem1, mem2, 0.95)]

        await manager.consolidate_memories(user_id="test-user")

        # mem1 should be deleted (lower importance)
        mock_repository.delete.assert_called_once_with(mem1.id)

    @pytest.mark.asyncio
    async def test_consolidate_memories_no_similar(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test consolidation when no similar memories exist."""
        mock_repository.find_similar_for_consolidation.return_value = []

        result = await manager.consolidate_memories(user_id="test-user")

        assert result == 0
        mock_repository.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_memory_stats(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting memory statistics."""
        mock_memory1 = MagicMock()
        mock_memory1.memory_type = MemoryType.TASK_RESULT.value
        mock_memory1.importance_score = 0.8

        mock_memory2 = MagicMock()
        mock_memory2.memory_type = MemoryType.LEARNING.value
        mock_memory2.importance_score = 0.6

        mock_memory3 = MagicMock()
        mock_memory3.memory_type = MemoryType.TASK_RESULT.value
        mock_memory3.importance_score = 0.7

        mock_repository.get_by_user_id.return_value = [mock_memory1, mock_memory2, mock_memory3]

        stats = await manager.get_memory_stats(user_id="test-user")

        assert stats["total_memories"] == 3
        assert stats["by_type"][MemoryType.TASK_RESULT.value] == 2
        assert stats["by_type"][MemoryType.LEARNING.value] == 1
        assert stats["average_importance"] == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_get_memory_stats_empty(
        self,
        manager: LongTermMemoryManager,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting stats when no memories exist."""
        mock_repository.get_by_user_id.return_value = []

        stats = await manager.get_memory_stats(user_id="test-user")

        assert stats["total_memories"] == 0
        assert stats["by_type"] == {}
        assert stats["average_importance"] == 0.0
