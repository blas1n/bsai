"""Tests for SummarizerAgent."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.core.summarizer import SummarizerAgent
from agent.db.models.enums import SnapshotType, TaskComplexity
from agent.llm import LLMModel, LLMResponse, UsageInfo
from agent.llm.schemas import ChatMessage


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create mock LLM client."""
    client = MagicMock()
    client.chat_completion = AsyncMock()
    return client


@pytest.fixture
def mock_router() -> MagicMock:
    """Create mock LLM router."""
    router = MagicMock()
    router.select_model.return_value = LLMModel(
        name="claude-3-5-sonnet-20241022",
        provider="anthropic",
        input_price_per_1k=Decimal("0.003"),
        output_price_per_1k=Decimal("0.015"),
        context_window=200000,
        supports_streaming=True,
    )
    router.calculate_cost.return_value = Decimal("0.004")
    router.estimate_tokens.return_value = 5000
    return router


@pytest.fixture
def mock_prompt_manager() -> MagicMock:
    """Create mock PromptManager."""
    manager = MagicMock()
    manager.render.return_value = "Summary prompt"
    return manager


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def summarizer(
    mock_llm_client: MagicMock,
    mock_router: MagicMock,
    mock_prompt_manager: MagicMock,
    mock_session: AsyncMock,
) -> SummarizerAgent:
    """Create SummarizerAgent with mocked dependencies."""
    with patch("agent.core.summarizer.get_container") as mock_get_container:
        mock_container = MagicMock()
        mock_container.prompt_manager = mock_prompt_manager
        mock_get_container.return_value = mock_container

        agent = SummarizerAgent(
            llm_client=mock_llm_client,
            router=mock_router,
            session=mock_session,
        )
        # Mock the snapshot_repo that gets created internally
        agent.snapshot_repo = MagicMock()
        agent.snapshot_repo.create = AsyncMock()
        return agent


class TestSummarizerAgent:
    """Test SummarizerAgent functionality."""

    @pytest.mark.asyncio
    async def test_compress_context_success(
        self,
        summarizer: SummarizerAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test successful context compression."""
        session_id = uuid4()
        task_id = uuid4()
        conversation_history = [
            ChatMessage(role="user", content="Build a scraper"),
            ChatMessage(role="assistant", content="I'll help with that"),
            ChatMessage(role="user", content="Add error handling"),
            ChatMessage(role="assistant", content="Error handling added"),
            ChatMessage(role="user", content="Test it"),
        ]
        current_context_size = 10000
        max_context_size = 8000

        # Mock LLM response
        mock_response = LLMResponse(
            content="Summary: Built web scraper with error handling",
            usage=UsageInfo(input_tokens=800, output_tokens=200, total_tokens=1000),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        summary, preserved = await summarizer.compress_context(
            session_id=session_id,
            task_id=task_id,
            conversation_history=conversation_history,
            current_context_size=current_context_size,
            max_context_size=max_context_size,
        )

        # Verify
        assert summary == "Summary: Built web scraper with error handling"
        assert len(preserved) > 0  # Should preserve recent messages
        assert preserved[-1].content == "Test it"  # Most recent message preserved

        # Check snapshot was created
        summarizer.snapshot_repo.create.assert_called_once()
        snapshot_call = summarizer.snapshot_repo.create.call_args
        assert snapshot_call.kwargs["snapshot_type"] == SnapshotType.AUTO
        assert snapshot_call.kwargs["session_id"] == session_id
        assert snapshot_call.kwargs["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_compress_context_preserve_calculation(
        self,
        summarizer: SummarizerAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test preservation count calculation."""
        session_id = uuid4()
        task_id = uuid4()
        conversation_history = [ChatMessage(role="user", content=f"Message {i}") for i in range(10)]
        current_context_size = 12000
        max_context_size = 10000

        # Mock LLM response
        mock_response = LLMResponse(
            content="Summary of conversation",
            usage=UsageInfo(input_tokens=800, output_tokens=200, total_tokens=1000),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        summary, preserved = await summarizer.compress_context(
            session_id=session_id,
            task_id=task_id,
            conversation_history=conversation_history,
            current_context_size=current_context_size,
            max_context_size=max_context_size,
        )

        # Verify preservation logic
        # Should preserve some messages
        assert len(preserved) >= 1  # At least some messages preserved
        assert len(preserved) < len(conversation_history)  # But not all

    @pytest.mark.asyncio
    async def test_create_checkpoint_success(
        self,
        summarizer: SummarizerAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test manual checkpoint creation."""
        session_id = uuid4()
        task_id = uuid4()
        conversation_history = [
            ChatMessage(role="user", content="Build feature"),
            ChatMessage(role="assistant", content="Feature built"),
        ]

        # Mock LLM response
        mock_response = LLMResponse(
            content="Checkpoint: Feature implementation complete",
            usage=UsageInfo(input_tokens=600, output_tokens=150, total_tokens=750),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        checkpoint = await summarizer.create_manual_snapshot(
            session_id=session_id,
            task_id=task_id,
            conversation_history=conversation_history,
        )

        # Verify
        assert checkpoint == "Checkpoint: Feature implementation complete"

        # Check snapshot was created with MANUAL type
        summarizer.snapshot_repo.create.assert_called_once()
        snapshot_call = summarizer.snapshot_repo.create.call_args
        assert snapshot_call.kwargs["snapshot_type"] == SnapshotType.MANUAL
        assert snapshot_call.kwargs["session_id"] == session_id
        assert snapshot_call.kwargs["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_compress_context_empty_history(
        self,
        summarizer: SummarizerAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test handling of empty conversation history."""
        session_id = uuid4()
        task_id = uuid4()
        conversation_history: list[ChatMessage] = []
        current_context_size = 0
        max_context_size = 8000

        # Mock LLM response
        mock_response = LLMResponse(
            content="No conversation to summarize",
            usage=UsageInfo(input_tokens=50, output_tokens=10, total_tokens=60),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        summary, preserved = await summarizer.compress_context(
            session_id=session_id,
            task_id=task_id,
            conversation_history=conversation_history,
            current_context_size=current_context_size,
            max_context_size=max_context_size,
        )

        # Should handle gracefully
        assert isinstance(summary, str)
        assert len(preserved) == 0

    @pytest.mark.asyncio
    async def test_compress_context_all_preserved(
        self,
        summarizer: SummarizerAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test when all messages should be preserved."""
        session_id = uuid4()
        task_id = uuid4()
        conversation_history = [
            ChatMessage(role="user", content="Short message"),
        ]
        current_context_size = 1000
        max_context_size = 10000  # Well under limit

        # Mock LLM response
        mock_response = LLMResponse(
            content="Brief summary",
            usage=UsageInfo(input_tokens=50, output_tokens=10, total_tokens=60),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        summary, preserved = await summarizer.compress_context(
            session_id=session_id,
            task_id=task_id,
            conversation_history=conversation_history,
            current_context_size=current_context_size,
            max_context_size=max_context_size,
        )

        # When well under limit, should preserve most/all messages
        assert len(preserved) >= 1

    @pytest.mark.asyncio
    async def test_create_checkpoint_cost_tracking(
        self,
        summarizer: SummarizerAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test cost tracking for checkpoint creation."""
        session_id = uuid4()
        task_id = uuid4()
        conversation_history = [
            ChatMessage(role="user", content="Test"),
        ]

        # Mock LLM response
        mock_response = LLMResponse(
            content="Checkpoint created",
            usage=UsageInfo(input_tokens=400, output_tokens=100, total_tokens=500),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        await summarizer.create_manual_snapshot(
            session_id=session_id,
            task_id=task_id,
            conversation_history=conversation_history,
        )

        # Verify LLM was called
        mock_llm_client.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_compress_context_model_selection(
        self,
        summarizer: SummarizerAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test that MODERATE complexity model is used."""
        session_id = uuid4()
        task_id = uuid4()
        conversation_history = [
            ChatMessage(role="user", content="Test"),
        ]

        # Mock LLM response
        mock_response = LLMResponse(
            content="Summary",
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        await summarizer.compress_context(
            session_id=session_id,
            task_id=task_id,
            conversation_history=conversation_history,
            current_context_size=10000,
            max_context_size=8000,
        )

        # Verify MODERATE complexity was used
        mock_router.select_model.assert_called_once_with(TaskComplexity.MODERATE)
