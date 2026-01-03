"""LiteLLM client tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from agent.llm.client import LiteLLMClient
from agent.llm.schemas import ChatMessage, LLMRequest

if TYPE_CHECKING:
    pass


def get_unwrapped(method: Any) -> Callable[..., Any]:
    """Get the unwrapped function from a tenacity-decorated method."""
    return method.__wrapped__


def create_mock_response(
    content: str = "Response",
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 10,
    model: str = "gpt-4",
) -> MagicMock:
    """Create a mock LiteLLM response with proper attribute access."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    mock_response.choices[0].finish_reason = finish_reason
    mock_response.usage.prompt_tokens = prompt_tokens
    mock_response.usage.completion_tokens = completion_tokens
    mock_response.usage.total_tokens = prompt_tokens + completion_tokens
    mock_response.model = model
    return mock_response


@pytest.fixture
def client() -> LiteLLMClient:
    """Create LiteLLM client."""
    return LiteLLMClient()


@pytest.fixture
def sample_request() -> LLMRequest:
    """Create sample LLM request."""
    return LLMRequest(
        model="gpt-4",
        messages=[
            ChatMessage(role="system", content="You are helpful."),
            ChatMessage(role="user", content="Hello!"),
        ],
        temperature=0.7,
        max_tokens=1000,
    )


class TestChatCompletion:
    """Tests for chat_completion method."""

    @pytest.mark.asyncio
    async def test_successful_completion(
        self,
        client: LiteLLMClient,
        sample_request: LLMRequest,
    ) -> None:
        """Returns response on successful completion."""
        mock_response = create_mock_response(
            content="Hello! How can I help?",
            finish_reason="stop",
            prompt_tokens=20,
            completion_tokens=10,
            model="gpt-4",
        )

        with patch("agent.llm.client.litellm.acompletion") as mock_completion:
            mock_completion.return_value = mock_response

            result = await client.chat_completion(sample_request)

            assert result.content == "Hello! How can I help?"
            assert result.usage.input_tokens == 20
            assert result.usage.output_tokens == 10
            assert result.finish_reason == "stop"
            mock_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_model_parameters(
        self,
        client: LiteLLMClient,
    ) -> None:
        """Passes all parameters to LiteLLM."""
        request = LLMRequest(
            model="claude-3-opus",
            messages=[ChatMessage(role="user", content="Test")],
            temperature=0.5,
            max_tokens=500,
            api_base="https://custom.api.com",
            api_key="custom-key",
        )

        mock_response = create_mock_response(
            content="Response",
            prompt_tokens=5,
            completion_tokens=5,
            model="claude-3-opus",
        )

        with patch("agent.llm.client.litellm.acompletion") as mock_completion:
            mock_completion.return_value = mock_response

            await client.chat_completion(request)

            call_kwargs = mock_completion.call_args[1]
            assert call_kwargs["model"] == "claude-3-opus"
            assert call_kwargs["temperature"] == 0.5
            assert call_kwargs["max_tokens"] == 500
            assert call_kwargs["api_base"] == "https://custom.api.com"
            assert call_kwargs["api_key"] == "custom-key"

    @pytest.mark.asyncio
    async def test_handles_missing_max_tokens(
        self,
        client: LiteLLMClient,
    ) -> None:
        """Does not pass max_tokens when None."""
        request = LLMRequest(
            model="gpt-4",
            messages=[ChatMessage(role="user", content="Test")],
            max_tokens=None,
        )

        mock_response = create_mock_response(
            content="Response",
            prompt_tokens=5,
            completion_tokens=5,
        )

        with patch("agent.llm.client.litellm.acompletion") as mock_completion:
            mock_completion.return_value = mock_response

            await client.chat_completion(request)

            call_kwargs = mock_completion.call_args[1]
            assert "max_tokens" not in call_kwargs

    @pytest.mark.asyncio
    async def test_logs_completion(
        self,
        client: LiteLLMClient,
        sample_request: LLMRequest,
    ) -> None:
        """Logs completion start and success."""
        mock_response = create_mock_response()

        with (
            patch("agent.llm.client.litellm.acompletion", return_value=mock_response),
            patch("agent.llm.client.logger") as mock_logger,
        ):
            await client.chat_completion(sample_request)

            assert mock_logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_failure(
        self,
        client: LiteLLMClient,
        sample_request: LLMRequest,
    ) -> None:
        """Retries on transient failures."""
        mock_response = create_mock_response()

        call_count = 0

        async def mock_completion(**kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Transient error")
            return mock_response

        with (
            patch("agent.llm.client.litellm.acompletion", side_effect=mock_completion),
            patch("tenacity.nap.time.sleep", return_value=None),  # Skip retry delays
        ):
            result = await client.chat_completion(sample_request)

            assert result.content == "Response"
            assert call_count == 3  # Initial call + 2 retries

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(
        self,
        client: LiteLLMClient,
        sample_request: LLMRequest,
    ) -> None:
        """Raises exception after all retries fail."""
        with (
            patch("agent.llm.client.litellm.acompletion") as mock_completion,
            patch("tenacity.nap.time.sleep", return_value=None),  # Skip retry delays
        ):
            mock_completion.side_effect = Exception("Persistent error")

            with pytest.raises(Exception, match="Persistent error"):
                await client.chat_completion(sample_request)


def create_stream_chunk(content: str | None = None) -> MagicMock:
    """Create a mock stream chunk with proper attribute access."""
    chunk = MagicMock()
    if content is not None:
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = content
    else:
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = None
    return chunk


class TestStreamCompletion:
    """Tests for stream_completion method."""

    @pytest.mark.asyncio
    async def test_yields_content_chunks(
        self,
        client: LiteLLMClient,
        sample_request: LLMRequest,
    ) -> None:
        """Yields content from stream chunks."""

        async def mock_stream():
            for content in ["Hello", " World", "!"]:
                yield create_stream_chunk(content)

        with patch("agent.llm.client.litellm.acompletion") as mock_completion:
            mock_completion.return_value = mock_stream()

            chunks = []
            async for chunk in get_unwrapped(client.stream_completion)(client, sample_request):
                chunks.append(chunk)

            assert chunks == ["Hello", " World", "!"]

    @pytest.mark.asyncio
    async def test_skips_empty_chunks(
        self,
        client: LiteLLMClient,
        sample_request: LLMRequest,
    ) -> None:
        """Skips chunks without content."""

        async def mock_stream():
            # Chunk with no content
            yield create_stream_chunk(None)
            # Chunk with content
            yield create_stream_chunk("Hello")
            # Empty choices
            empty_chunk = MagicMock()
            empty_chunk.choices = []
            yield empty_chunk
            # Chunk with content
            yield create_stream_chunk("!")

        with patch("agent.llm.client.litellm.acompletion") as mock_completion:
            mock_completion.return_value = mock_stream()

            chunks = []
            async for chunk in get_unwrapped(client.stream_completion)(client, sample_request):
                chunks.append(chunk)

            assert chunks == ["Hello", "!"]

    @pytest.mark.asyncio
    async def test_enables_stream_parameter(
        self,
        client: LiteLLMClient,
        sample_request: LLMRequest,
    ) -> None:
        """Sets stream=True in API call."""

        async def mock_stream():
            yield create_stream_chunk("Test")

        with patch("agent.llm.client.litellm.acompletion") as mock_completion:
            mock_completion.return_value = mock_stream()

            chunks = []
            async for chunk in get_unwrapped(client.stream_completion)(client, sample_request):
                chunks.append(chunk)

            call_kwargs = mock_completion.call_args[1]
            assert call_kwargs["stream"] is True

    @pytest.mark.asyncio
    async def test_logs_stream_completion(
        self,
        client: LiteLLMClient,
        sample_request: LLMRequest,
    ) -> None:
        """Logs stream start and success."""

        async def mock_stream():
            yield create_stream_chunk("Test")

        with (
            patch("agent.llm.client.litellm.acompletion", return_value=mock_stream()),
            patch("agent.llm.client.logger") as mock_logger,
        ):
            chunks = []
            async for chunk in get_unwrapped(client.stream_completion)(client, sample_request):
                chunks.append(chunk)

            assert mock_logger.info.call_count == 2
