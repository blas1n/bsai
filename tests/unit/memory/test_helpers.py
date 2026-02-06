"""Unit tests for memory helper functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from litellm.exceptions import RateLimitError

from bsai.db.models.enums import MemoryType
from bsai.memory.helpers import get_memory_context, store_qa_learning, store_task_memory


class TestGetMemoryContext:
    """Tests for get_memory_context helper."""

    @pytest.mark.asyncio
    async def test_get_memory_context_success(self) -> None:
        """Test successful memory context retrieval."""
        mock_memory = MagicMock()
        mock_memory.id = uuid4()
        mock_memory.summary = "Previous task"
        mock_memory.memory_type = MemoryType.TASK_RESULT.value

        mock_manager = MagicMock()
        mock_manager.search_similar = AsyncMock(return_value=[(mock_memory, 0.85)])
        mock_manager.get_relevant_context = AsyncMock(return_value="Formatted context")

        memories, context = await get_memory_context(
            manager=mock_manager,
            user_id="test-user",
            original_request="Test task",
        )

        assert len(memories) == 1
        assert memories[0]["summary"] == "Previous task"
        assert context == "Formatted context"

    @pytest.mark.asyncio
    async def test_get_memory_context_no_results(self) -> None:
        """Test memory context when no memories found."""
        mock_manager = MagicMock()
        mock_manager.search_similar = AsyncMock(return_value=[])
        mock_manager.get_relevant_context = AsyncMock(return_value="")

        memories, context = await get_memory_context(
            manager=mock_manager,
            user_id="test-user",
            original_request="Test task",
        )

        assert memories == []
        assert context == ""

    @pytest.mark.asyncio
    async def test_get_memory_context_transient_error_returns_empty(self) -> None:
        """Test that transient errors (rate limit) return empty results gracefully."""
        mock_manager = MagicMock()
        # Transient errors like RateLimitError should return empty (graceful degradation)
        mock_manager.search_similar = AsyncMock(
            side_effect=RateLimitError("Rate limit exceeded", "test", "test")
        )

        memories, context = await get_memory_context(
            manager=mock_manager,
            user_id="test-user",
            original_request="Test task",
        )

        assert memories == []
        assert context == ""

    @pytest.mark.asyncio
    async def test_get_memory_context_unexpected_error_raises(self) -> None:
        """Test that unexpected errors are propagated."""
        mock_manager = MagicMock()
        # Non-transient errors should be re-raised
        mock_manager.search_similar = AsyncMock(side_effect=ValueError("Unexpected error"))

        with pytest.raises(ValueError, match="Unexpected error"):
            await get_memory_context(
                manager=mock_manager,
                user_id="test-user",
                original_request="Test task",
            )


class TestStoreTaskMemory:
    """Tests for store_task_memory helper."""

    @pytest.mark.asyncio
    async def test_store_task_memory_success(self) -> None:
        """Test successful task memory storage."""
        milestones = [
            {"description": "Step 1", "status": MagicMock(value="passed")},
            {"description": "Step 2", "status": MagicMock(value="passed")},
        ]

        mock_manager = MagicMock()
        mock_manager.store_task_result = AsyncMock()

        await store_task_memory(
            manager=mock_manager,
            user_id="test-user",
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Build feature",
            final_response="Feature built",
            milestones=milestones,
        )

        mock_manager.store_task_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_task_memory_transient_error_silent(self) -> None:
        """Test that transient storage errors are handled silently."""
        mock_manager = MagicMock()
        # Transient errors like RateLimitError should be handled silently
        mock_manager.store_task_result = AsyncMock(
            side_effect=RateLimitError("Rate limit exceeded", "test", "test")
        )

        # Should not raise
        await store_task_memory(
            manager=mock_manager,
            user_id="test-user",
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Build feature",
            final_response="Feature built",
            milestones=[],
        )

    @pytest.mark.asyncio
    async def test_store_task_memory_unexpected_error_raises(self) -> None:
        """Test that unexpected storage errors are propagated."""
        mock_manager = MagicMock()
        # Non-transient errors should be re-raised
        mock_manager.store_task_result = AsyncMock(side_effect=ValueError("Unexpected error"))

        with pytest.raises(ValueError, match="Unexpected error"):
            await store_task_memory(
                manager=mock_manager,
                user_id="test-user",
                session_id=uuid4(),
                task_id=uuid4(),
                original_request="Build feature",
                final_response="Feature built",
                milestones=[],
            )


class TestStoreQaLearning:
    """Tests for store_qa_learning helper."""

    @pytest.mark.asyncio
    async def test_store_qa_learning_success(self) -> None:
        """Test successful QA learning storage."""
        mock_manager = MagicMock()
        mock_manager.store_qa_learning = AsyncMock()

        await store_qa_learning(
            manager=mock_manager,
            user_id="test-user",
            session_id=uuid4(),
            task_id=uuid4(),
            previous_output="Initial output",
            qa_feedback="Needs improvement",
            improved_output="Better output",
        )

        mock_manager.store_qa_learning.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_qa_learning_transient_error_silent(self) -> None:
        """Test that transient storage errors are handled silently."""
        mock_manager = MagicMock()
        # Transient errors like RateLimitError should be handled silently
        mock_manager.store_qa_learning = AsyncMock(
            side_effect=RateLimitError("Rate limit exceeded", "test", "test")
        )

        # Should not raise
        await store_qa_learning(
            manager=mock_manager,
            user_id="test-user",
            session_id=uuid4(),
            task_id=uuid4(),
            previous_output="Output",
            qa_feedback="Feedback",
            improved_output="Improved",
        )

    @pytest.mark.asyncio
    async def test_store_qa_learning_unexpected_error_raises(self) -> None:
        """Test that unexpected storage errors are propagated."""
        mock_manager = MagicMock()
        # Non-transient errors should be re-raised
        mock_manager.store_qa_learning = AsyncMock(side_effect=ValueError("Unexpected error"))

        with pytest.raises(ValueError, match="Unexpected error"):
            await store_qa_learning(
                manager=mock_manager,
                user_id="test-user",
                session_id=uuid4(),
                task_id=uuid4(),
                previous_output="Output",
                qa_feedback="Feedback",
                improved_output="Improved",
            )
