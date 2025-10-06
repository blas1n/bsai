"""
Tests for OpenAI LLM Provider
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
from agent_platform.core.llm.providers.openai_provider import OpenAIProvider


class TestOpenAIProvider:
    """Test OpenAI provider implementation"""

    @pytest.fixture
    def mock_openai_client(self):
        """Create mock OpenAI client"""
        mock = MagicMock()
        mock.chat = MagicMock()
        mock.chat.completions = MagicMock()
        return mock

    @pytest.fixture
    def provider(self, mock_openai_client):
        """Create OpenAI provider with mocked client"""
        with patch("agent_platform.core.llm.providers.openai_provider.AsyncOpenAI") as mock_cls:
            mock_cls.return_value = mock_openai_client
            provider = OpenAIProvider(api_key="test-api-key")
            return provider

    @pytest.mark.asyncio
    async def test_chat_completion(self, provider, mock_openai_client):
        """Test chat completion with OpenAI"""
        # Arrange
        messages = [ChatMessage(role="user", content="What is 2+2?")]
        request = ChatRequest(messages=messages, model="gpt-4")

        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "4"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 1
        mock_response.usage.total_tokens = 11
        mock_response.model = "gpt-4-0613"

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Act
        response = await provider.chat_completion(request)

        # Assert
        assert response.content == "4"
        assert response.role == "assistant"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 1
        assert response.usage.total_tokens == 11
        assert response.model == "gpt-4-0613"
        assert response.finish_reason == "stop"

        # Verify API was called correctly
        mock_openai_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4"
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"
        assert call_kwargs["messages"][0]["content"] == "What is 2+2?"
        assert call_kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_chat_completion_with_custom_params(self, provider, mock_openai_client):
        """Test chat completion with custom parameters"""
        # Arrange
        messages = [
            ChatMessage(role="system", content="You are helpful"),
            ChatMessage(role="user", content="Hello"),
        ]
        request = ChatRequest(
            messages=messages,
            model="gpt-3.5-turbo",
            temperature=0.5,
            max_tokens=100,
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi there!"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage.prompt_tokens = 15
        mock_response.usage.completion_tokens = 3
        mock_response.usage.total_tokens = 18
        mock_response.model = "gpt-3.5-turbo-0125"

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Act
        response = await provider.chat_completion(request)

        # Assert
        assert response.content == "Hi there!"

        # Verify parameters
        call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 100
        assert len(call_kwargs["messages"]) == 2

    @pytest.mark.asyncio
    async def test_stream_completion(self, provider, mock_openai_client):
        """Test streaming chat completion"""
        # Arrange
        messages = [ChatMessage(role="user", content="Count to 3")]
        request = ChatRequest(messages=messages, model="gpt-4", stream=True)

        # Mock streaming response
        async def mock_stream():
            chunks = ["1", ", ", "2", ", ", "3"]
            for chunk_text in chunks:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = chunk_text
                yield chunk

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        # Act
        chunks = []
        async for chunk in provider.stream_completion(request):
            chunks.append(chunk)

        # Assert
        assert chunks == ["1", ", ", "2", ", ", "3"]

        # Verify stream=True was passed
        call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["stream"] is True

    def test_get_token_count(self, provider):
        """Test token counting using tiktoken"""
        # Test with simple text
        text = "Hello, how are you?"
        count = provider.get_token_count(text)

        # tiktoken should return approximate token count
        assert count > 0
        assert isinstance(count, int)

        # Test with longer text
        long_text = "This is a longer text that should have more tokens. " * 10
        long_count = provider.get_token_count(long_text)
        assert long_count > count

    def test_get_model_info(self, provider):
        """Test getting model information"""
        info = provider.get_model_info()

        assert info.provider == "openai"
        assert info.model_name in ["gpt-4", "gpt-3.5-turbo"]  # Should have a default
        assert info.context_window > 0
        assert isinstance(info.supports_streaming, bool)
        assert info.supports_streaming is True

    @pytest.mark.asyncio
    async def test_error_handling_api_error(self, provider, mock_openai_client):
        """Test handling of OpenAI API errors"""
        from httpx import Request, Response
        from openai import APIError

        messages = [ChatMessage(role="user", content="test")]
        request_obj = ChatRequest(messages=messages, model="gpt-4")

        # Create a mock HTTP request and response for APIError
        mock_request = Request("POST", "https://api.openai.com/v1/chat/completions")

        # Mock API error with required request parameter
        mock_openai_client.chat.completions.create = AsyncMock(
            side_effect=APIError("API Error", request=mock_request, body=None)
        )

        # Should raise the error (will be handled by retry logic in real implementation)
        with pytest.raises(APIError):
            await provider.chat_completion(request_obj)

    @pytest.mark.asyncio
    async def test_error_handling_rate_limit(self, provider, mock_openai_client):
        """Test handling of rate limit errors"""
        from httpx import Request, Response
        from openai import RateLimitError

        messages = [ChatMessage(role="user", content="test")]
        request_obj = ChatRequest(messages=messages, model="gpt-4")

        # Create mock HTTP request and response for RateLimitError
        mock_request = Request("POST", "https://api.openai.com/v1/chat/completions")
        mock_response = Response(429, request=mock_request)

        # Mock rate limit error with required parameters
        mock_openai_client.chat.completions.create = AsyncMock(
            side_effect=RateLimitError("Rate limit exceeded", response=mock_response, body=None)
        )

        # Should raise the error (will be handled by retry logic in real implementation)
        with pytest.raises(RateLimitError):
            await provider.chat_completion(request_obj)

    def test_init_with_env_var(self):
        """Test initialization with environment variable"""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-api-key"}):
            with patch("agent_platform.core.llm.providers.openai_provider.AsyncOpenAI") as mock_cls:
                provider = OpenAIProvider()

                # Should use environment variable
                mock_cls.assert_called_once()
                assert mock_cls.call_args.kwargs["api_key"] == "env-api-key"

    def test_init_without_api_key(self):
        """Test initialization fails without API key"""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                OpenAIProvider()
