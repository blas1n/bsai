"""Tests for context management nodes."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.graph.nodes.context import check_context_node, summarize_node
from agent.graph.state import AgentState
from agent.llm import ChatMessage


class TestCheckContextNode:
    """Tests for check_context_node."""

    @pytest.mark.asyncio
    async def test_needs_compression(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test context check when compression is needed."""
        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
            current_context_tokens=90000,
            max_context_tokens=100000,
        )

        with patch("agent.graph.nodes.context.SummarizerAgent") as MockSummarizer:
            mock_summarizer = MagicMock()
            mock_summarizer.should_compress.return_value = True
            MockSummarizer.return_value = mock_summarizer

            result = await check_context_node(state, mock_config, mock_session)

            assert result["needs_compression"] is True

    @pytest.mark.asyncio
    async def test_no_compression_needed(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test context check when compression is not needed."""
        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
            current_context_tokens=10000,
            max_context_tokens=100000,
        )

        with patch("agent.graph.nodes.context.SummarizerAgent") as MockSummarizer:
            mock_summarizer = MagicMock()
            mock_summarizer.should_compress.return_value = False
            MockSummarizer.return_value = mock_summarizer

            result = await check_context_node(state, mock_config, mock_session)

            assert result["needs_compression"] is False


class TestSummarizeNode:
    """Tests for summarize_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test successful context summarization."""
        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
            context_messages=[
                ChatMessage(role="user", content="First message"),
                ChatMessage(role="assistant", content="First response"),
                ChatMessage(role="user", content="Second message"),
                ChatMessage(role="assistant", content="Second response"),
            ],
            current_context_tokens=90000,
            max_context_tokens=100000,
        )

        with patch("agent.graph.nodes.context.SummarizerAgent") as MockSummarizer:
            mock_summarizer = AsyncMock()
            remaining = [ChatMessage(role="assistant", content="Second response")]
            mock_summarizer.compress_context.return_value = ("Context summary", remaining)
            MockSummarizer.return_value = mock_summarizer

            result = await summarize_node(state, mock_config, mock_session)

            assert result["context_summary"] == "Context summary"
            assert result["needs_compression"] is False
            assert len(result["context_messages"]) == 2  # summary + remaining
