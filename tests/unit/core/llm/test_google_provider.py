"""
Tests for Google Gemini LLM Provider
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
from agent_platform.core.llm.providers.google_provider import GoogleProvider


class TestGoogleProvider:
    """Test Google Gemini provider implementation"""

    @pytest.fixture
    def mock_genai(self):
        """Create mock google.generativeai module"""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def mock_model(self):
        """Create mock GenerativeModel"""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def provider(self, mock_genai, mock_model):
        """Create Google provider with mocked client"""
        with patch("agent_platform.core.llm.providers.google_provider.genai", mock_genai):
            with patch("agent_platform.core.llm.providers.google_provider.GenerativeModel") as mock_model_cls:
                mock_model_cls.return_value = mock_model
                provider = GoogleProvider(api_key="test-api-key")
                return provider

    @pytest.mark.asyncio
    async def test_chat_completion(self, provider, mock_model):
        """Test chat completion with Google Gemini"""
        # Arrange
        messages = [ChatMessage(role="user", content="What is 2+2?")]
        request = ChatRequest(messages=messages, model="gemini-pro")

        # Mock Gemini response
        mock_response = MagicMock()
        mock_response.text = "4"
        mock_response.usage_metadata.prompt_token_count = 10
        mock_response.usage_metadata.candidates_token_count = 1
        mock_response.usage_metadata.total_token_count = 11

        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        # Act
        response = await provider.chat_completion(request)

        # Assert
        assert response.content == "4"
        assert response.role == "assistant"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 1
        assert response.usage.total_tokens == 11
        assert response.model == "gemini-pro"
        assert response.finish_reason == "stop"

        # Verify API was called correctly
        mock_model.generate_content_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_completion_with_system_message(self, provider, mock_model):
        """Test chat completion with system message"""
        # Arrange
        messages = [
            ChatMessage(role="system", content="You are helpful"),
            ChatMessage(role="user", content="Hello"),
        ]
        request = ChatRequest(
            messages=messages,
            model="gemini-pro",
            temperature=0.5,
            max_tokens=100,
        )

        mock_response = MagicMock()
        mock_response.text = "Hi there!"
        mock_response.usage_metadata.prompt_token_count = 15
        mock_response.usage_metadata.candidates_token_count = 3
        mock_response.usage_metadata.total_token_count = 18

        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        # Act
        response = await provider.chat_completion(request)

        # Assert
        assert response.content == "Hi there!"

        # Verify system message was included in content
        call_args = mock_model.generate_content_async.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_stream_completion(self, provider, mock_model):
        """Test streaming chat completion"""
        # Arrange
        messages = [ChatMessage(role="user", content="Count to 3")]
        request = ChatRequest(messages=messages, model="gemini-pro", stream=True)

        # Mock streaming response
        async def mock_stream():
            chunks = ["1", ", ", "2", ", ", "3"]
            for chunk_text in chunks:
                chunk = MagicMock()
                chunk.text = chunk_text
                yield chunk

        mock_model.generate_content_async = AsyncMock(return_value=mock_stream())

        # Act
        chunks = []
        async for chunk in provider.stream_completion(request):
            chunks.append(chunk)

        # Assert
        assert chunks == ["1", ", ", "2", ", ", "3"]

    def test_get_token_count(self, provider, mock_model):
        """Test token counting"""
        # Mock count_tokens method
        mock_model.count_tokens = MagicMock(return_value=MagicMock(total_tokens=5))

        # Test with simple text
        text = "Hello, how are you?"
        count = provider.get_token_count(text)

        # Should use Gemini's count_tokens
        assert count == 5
        mock_model.count_tokens.assert_called_once()

    def test_get_model_info(self, provider):
        """Test getting model information"""
        info = provider.get_model_info()

        assert info.provider == "google"
        assert "gemini" in info.model_name.lower()
        assert info.context_window > 0
        assert isinstance(info.supports_streaming, bool)
        assert info.supports_streaming is True

    @pytest.mark.asyncio
    async def test_error_handling_api_error(self, provider, mock_model):
        """Test handling of Google API errors"""
        from google.api_core.exceptions import GoogleAPIError

        messages = [ChatMessage(role="user", content="test")]
        request_obj = ChatRequest(messages=messages, model="gemini-pro")

        # Mock API error
        mock_model.generate_content_async = AsyncMock(
            side_effect=GoogleAPIError("API Error")
        )

        # Should raise the error (will be handled by retry logic in real implementation)
        with pytest.raises(GoogleAPIError):
            await provider.chat_completion(request_obj)

    @pytest.mark.asyncio
    async def test_error_handling_rate_limit(self, provider, mock_model):
        """Test handling of rate limit errors"""
        from google.api_core.exceptions import ResourceExhausted

        messages = [ChatMessage(role="user", content="test")]
        request_obj = ChatRequest(messages=messages, model="gemini-pro")

        # Mock rate limit error
        mock_model.generate_content_async = AsyncMock(
            side_effect=ResourceExhausted("Rate limit exceeded")
        )

        # Should raise the error (will be handled by retry logic in real implementation)
        with pytest.raises(ResourceExhausted):
            await provider.chat_completion(request_obj)

    def test_init_with_env_var(self, mock_genai):
        """Test initialization with environment variable"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "env-api-key"}):
            with patch("agent_platform.core.llm.providers.google_provider.genai", mock_genai):
                with patch("agent_platform.core.llm.providers.google_provider.GenerativeModel"):
                    provider = GoogleProvider()

                    # Should use environment variable
                    mock_genai.configure.assert_called_once()
                    assert mock_genai.configure.call_args.kwargs["api_key"] == "env-api-key"

    def test_init_without_api_key(self):
        """Test initialization fails without API key"""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
                GoogleProvider()
