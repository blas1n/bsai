"""
Tests for LiteLLM Fallback Provider
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
from agent_platform.core.llm.providers.litellm_provider import LiteLLMProvider


class TestLiteLLMProvider:
    """Test LiteLLM fallback provider implementation"""

    @pytest.fixture
    def provider(self):
        """Create LiteLLM provider"""
        return LiteLLMProvider()

    @pytest.mark.asyncio
    async def test_chat_completion(self, provider):
        """Test chat completion with LiteLLM"""
        # Arrange
        messages = [ChatMessage(role="user", content="What is 2+2?")]
        request = ChatRequest(messages=messages, model="gpt-3.5-turbo")

        # Mock LiteLLM response
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "4",
                        "role": "assistant",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 1,
                "total_tokens": 11,
            },
            "model": "gpt-3.5-turbo-0125",
        }

        with patch("agent_platform.core.llm.providers.litellm_provider.acompletion") as mock_acompletion:
            mock_acompletion.return_value = mock_response

            # Act
            response = await provider.chat_completion(request)

            # Assert
            assert response.content == "4"
            assert response.role == "assistant"
            assert response.usage.input_tokens == 10
            assert response.usage.output_tokens == 1
            assert response.usage.total_tokens == 11
            assert response.model == "gpt-3.5-turbo-0125"
            assert response.finish_reason == "stop"

            # Verify API was called correctly
            mock_acompletion.assert_called_once()
            call_kwargs = mock_acompletion.call_args.kwargs
            assert call_kwargs["model"] == "gpt-3.5-turbo"
            assert len(call_kwargs["messages"]) == 1
            assert call_kwargs["messages"][0]["role"] == "user"
            assert call_kwargs["messages"][0]["content"] == "What is 2+2?"
            assert call_kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_chat_completion_with_custom_params(self, provider):
        """Test chat completion with custom parameters"""
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

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "Hi there!",
                        "role": "assistant",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 3,
                "total_tokens": 18,
            },
            "model": "claude-3-sonnet-20240229",
        }

        with patch("agent_platform.core.llm.providers.litellm_provider.acompletion") as mock_acompletion:
            mock_acompletion.return_value = mock_response

            # Act
            response = await provider.chat_completion(request)

            # Assert
            assert response.content == "Hi there!"

            # Verify parameters
            call_kwargs = mock_acompletion.call_args.kwargs
            assert call_kwargs["temperature"] == 0.5
            assert call_kwargs["max_tokens"] == 100
            assert len(call_kwargs["messages"]) == 2

    @pytest.mark.asyncio
    async def test_stream_completion(self, provider):
        """Test streaming chat completion"""
        # Arrange
        messages = [ChatMessage(role="user", content="Count to 3")]
        request = ChatRequest(messages=messages, model="gpt-4", stream=True)

        # Mock streaming response
        async def mock_stream():
            chunks = [
                {"choices": [{"delta": {"content": "1"}}]},
                {"choices": [{"delta": {"content": ", "}}]},
                {"choices": [{"delta": {"content": "2"}}]},
                {"choices": [{"delta": {"content": ", "}}]},
                {"choices": [{"delta": {"content": "3"}}]},
            ]
            for chunk in chunks:
                yield chunk

        with patch("agent_platform.core.llm.providers.litellm_provider.acompletion") as mock_acompletion:
            mock_acompletion.return_value = mock_stream()

            # Act
            chunks = []
            async for chunk in provider.stream_completion(request):
                chunks.append(chunk)

            # Assert
            assert chunks == ["1", ", ", "2", ", ", "3"]

            # Verify stream=True was passed
            call_kwargs = mock_acompletion.call_args.kwargs
            assert call_kwargs["stream"] is True

    def test_get_token_count(self, provider):
        """Test token counting using tiktoken fallback"""
        # Test with simple text
        text = "Hello, how are you?"
        count = provider.get_token_count(text)

        # Should return approximate token count
        assert count > 0
        assert isinstance(count, int)

        # Test with longer text
        long_text = "This is a longer text that should have more tokens. " * 10
        long_count = provider.get_token_count(long_text)
        assert long_count > count

    def test_get_model_info(self, provider):
        """Test getting model information"""
        info = provider.get_model_info()

        assert info.provider == "litellm"
        assert info.model_name == "litellm-fallback"
        assert info.context_window > 0
        assert isinstance(info.supports_streaming, bool)
        assert info.supports_streaming is True

    @pytest.mark.asyncio
    async def test_error_handling_generic_error(self, provider):
        """Test handling of generic errors"""
        messages = [ChatMessage(role="user", content="test")]
        request_obj = ChatRequest(messages=messages, model="gpt-4")

        # Mock API error
        with patch("agent_platform.core.llm.providers.litellm_provider.acompletion") as mock_acompletion:
            mock_acompletion.side_effect = Exception("Generic Error")

            # Should raise the error
            with pytest.raises(Exception, match="Generic Error"):
                await provider.chat_completion(request_obj)

    @pytest.mark.asyncio
    async def test_multiple_models_support(self, provider):
        """Test that LiteLLM can handle multiple different models"""
        models_to_test = [
            "gpt-3.5-turbo",
            "gpt-4",
            "claude-3-opus-20240229",
            "gemini-pro",
            "command-r-plus",  # Cohere
        ]

        messages = [ChatMessage(role="user", content="test")]

        for model in models_to_test:
            request = ChatRequest(messages=messages, model=model)

            mock_response = {
                "choices": [
                    {
                        "message": {
                            "content": f"Response from {model}",
                            "role": "assistant",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 10,
                    "total_tokens": 15,
                },
                "model": model,
            }

            with patch("agent_platform.core.llm.providers.litellm_provider.acompletion") as mock_acompletion:
                mock_acompletion.return_value = mock_response

                # Act
                response = await provider.chat_completion(request)

                # Assert
                assert response.content == f"Response from {model}"
                assert response.model == model

                # Verify correct model was called
                call_kwargs = mock_acompletion.call_args.kwargs
                assert call_kwargs["model"] == model
