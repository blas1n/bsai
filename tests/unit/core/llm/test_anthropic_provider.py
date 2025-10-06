"""
Tests for Anthropic LLM Provider
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_platform.core.llm.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ModelInfo,
    UsageInfo,
)
from agent_platform.core.llm.providers.anthropic_provider import AnthropicProvider


class TestAnthropicProvider:
    """Test Anthropic provider implementation"""

    @pytest.fixture
    def mock_anthropic_client(self):
        """Create mock Anthropic client"""
        mock = MagicMock()
        mock.messages = MagicMock()
        return mock

    @pytest.fixture
    def provider(self, mock_anthropic_client):
        """Create Anthropic provider with mocked client"""
        with patch("agent_platform.core.llm.providers.anthropic_provider.AsyncAnthropic") as mock_cls:
            mock_cls.return_value = mock_anthropic_client
            provider = AnthropicProvider(api_key="test-api-key")
            return provider

    @pytest.mark.asyncio
    async def test_chat_completion(self, provider, mock_anthropic_client):
        """Test chat completion with Anthropic"""
        # Arrange
        messages = [ChatMessage(role="user", content="What is 2+2?")]
        request = ChatRequest(messages=messages, model="claude-3-opus-20240229")

        # Mock Anthropic response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "4"
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 1
        mock_response.model = "claude-3-opus-20240229"

        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        # Act
        response = await provider.chat_completion(request)

        # Assert
        assert response.content == "4"
        assert response.role == "assistant"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 1
        assert response.usage.total_tokens == 11
        assert response.model == "claude-3-opus-20240229"
        assert response.finish_reason == "end_turn"

        # Verify API was called correctly
        mock_anthropic_client.messages.create.assert_called_once()
        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-3-opus-20240229"
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"
        assert call_kwargs["messages"][0]["content"] == "What is 2+2?"
        assert call_kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_chat_completion_with_system_message(self, provider, mock_anthropic_client):
        """Test chat completion with system message"""
        # Arrange
        messages = [
            ChatMessage(role="system", content="You are helpful"),
            ChatMessage(role="user", content="Hello"),
        ]
        request = ChatRequest(
            messages=messages,
            model="claude-3-sonnet-20240229",
            temperature=0.5,
            max_tokens=100,
        )

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "Hi there!"
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 15
        mock_response.usage.output_tokens = 3
        mock_response.model = "claude-3-sonnet-20240229"

        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        # Act
        response = await provider.chat_completion(request)

        # Assert
        assert response.content == "Hi there!"

        # Verify parameters - system message should be separate
        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "You are helpful"
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 100
        assert len(call_kwargs["messages"]) == 1  # Only user message

    @pytest.mark.asyncio
    async def test_stream_completion(self, provider, mock_anthropic_client):
        """Test streaming chat completion"""
        # Arrange
        messages = [ChatMessage(role="user", content="Count to 3")]
        request = ChatRequest(messages=messages, model="claude-3-opus-20240229", stream=True)

        # Mock streaming response
        async def mock_stream():
            chunks = [
                {"content": "1"},
                {"content": ", "},
                {"content": "2"},
                {"content": ", "},
                {"content": "3"},
            ]
            for chunk_data in chunks:
                chunk = MagicMock()
                chunk.type = "content_block_delta"
                chunk.delta = MagicMock()
                chunk.delta.text = chunk_data["content"]
                yield chunk

        # Create async context manager mock
        mock_stream_context = MagicMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_stream())
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        mock_anthropic_client.messages.stream = MagicMock(return_value=mock_stream_context)

        # Act
        chunks = []
        async for chunk in provider.stream_completion(request):
            chunks.append(chunk)

        # Assert
        assert chunks == ["1", ", ", "2", ", ", "3"]

        # Verify stream was called
        mock_anthropic_client.messages.stream.assert_called_once()

    def test_get_token_count(self, provider, mock_anthropic_client):
        """Test token counting using Anthropic's count_tokens"""
        # Mock count_tokens method
        mock_anthropic_client.messages.count_tokens = MagicMock(return_value=5)

        # Test with simple text
        text = "Hello, how are you?"
        count = provider.get_token_count(text)

        # Should use Anthropic's count_tokens
        assert count == 5
        mock_anthropic_client.messages.count_tokens.assert_called_once()

    def test_get_model_info(self, provider):
        """Test getting model information"""
        info = provider.get_model_info()

        assert info.provider == "anthropic"
        assert info.model_name in ["claude-3-opus-20240229", "claude-3-sonnet-20240229"]
        assert info.context_window > 0
        assert isinstance(info.supports_streaming, bool)
        assert info.supports_streaming is True

    @pytest.mark.asyncio
    async def test_error_handling_api_error(self, provider, mock_anthropic_client):
        """Test handling of Anthropic API errors"""
        from anthropic import APIError
        from httpx import Request

        messages = [ChatMessage(role="user", content="test")]
        request_obj = ChatRequest(messages=messages, model="claude-3-opus-20240229")

        # Create mock HTTP request for APIError
        mock_request = Request("POST", "https://api.anthropic.com/v1/messages")

        # Mock API error
        mock_anthropic_client.messages.create = AsyncMock(
            side_effect=APIError("API Error", request=mock_request, body=None)
        )

        # Should raise the error (will be handled by retry logic in real implementation)
        with pytest.raises(APIError):
            await provider.chat_completion(request_obj)

    @pytest.mark.asyncio
    async def test_error_handling_rate_limit(self, provider, mock_anthropic_client):
        """Test handling of rate limit errors"""
        from anthropic import RateLimitError
        from httpx import Request, Response

        messages = [ChatMessage(role="user", content="test")]
        request_obj = ChatRequest(messages=messages, model="claude-3-opus-20240229")

        # Create mock HTTP request and response
        mock_request = Request("POST", "https://api.anthropic.com/v1/messages")
        mock_response = Response(429, request=mock_request)

        # Mock rate limit error
        mock_anthropic_client.messages.create = AsyncMock(
            side_effect=RateLimitError("Rate limit exceeded", response=mock_response, body=None)
        )

        # Should raise the error (will be handled by retry logic in real implementation)
        with pytest.raises(RateLimitError):
            await provider.chat_completion(request_obj)

    def test_init_with_env_var(self):
        """Test initialization with environment variable"""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-api-key"}):
            with patch("agent_platform.core.llm.providers.anthropic_provider.AsyncAnthropic") as mock_cls:
                provider = AnthropicProvider()

                # Should use environment variable
                mock_cls.assert_called_once()
                assert mock_cls.call_args.kwargs["api_key"] == "env-api-key"

    def test_init_without_api_key(self):
        """Test initialization fails without API key"""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                AnthropicProvider()
