"""LiteLLM client tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from agent.llm.client import LiteLLMClient
from agent.llm.schemas import ChatMessage, LLMRequest

if TYPE_CHECKING:
    pass


def get_unwrapped(method: Any) -> Callable[..., Any]:
    """Get the unwrapped function from a tenacity-decorated method."""
    return method.__wrapped__


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
        mock_response = {
            "choices": [
                {
                    "message": {"content": "Hello! How can I help?"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            },
            "model": "gpt-4",
        }

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

        mock_response = {
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            "model": "claude-3-opus",
        }

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

        mock_response = {
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            "model": "gpt-4",
        }

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
        mock_response = {
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            "model": "gpt-4",
        }

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
        mock_response = {
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            "model": "gpt-4",
        }

        call_count = 0

        async def mock_completion(**kwargs: object) -> dict[str, object]:
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
            chunks = [
                {"choices": [{"delta": {"content": "Hello"}}]},
                {"choices": [{"delta": {"content": " World"}}]},
                {"choices": [{"delta": {"content": "!"}}]},
            ]
            for chunk in chunks:
                yield chunk

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
            chunks = [
                {"choices": [{"delta": {}}]},  # No content
                {"choices": [{"delta": {"content": "Hello"}}]},
                {"choices": []},  # Empty choices
                {"choices": [{"delta": {"content": "!"}}]},
            ]
            for chunk in chunks:
                yield chunk

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
            yield {"choices": [{"delta": {"content": "Test"}}]}

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
            yield {"choices": [{"delta": {"content": "Test"}}]}

        with (
            patch("agent.llm.client.litellm.acompletion", return_value=mock_stream()),
            patch("agent.llm.client.logger") as mock_logger,
        ):
            chunks = []
            async for chunk in get_unwrapped(client.stream_completion)(client, sample_request):
                chunks.append(chunk)

            assert mock_logger.info.call_count == 2
