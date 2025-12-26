"""
Tests for LLM base classes and interfaces
"""

import pytest
from agent_platform.core.llm.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    LLMProvider,
    ModelInfo,
    UsageInfo,
)


class TestChatMessage:
    """Test ChatMessage model"""

    def test_create_user_message(self):
        """Test creating a user message"""
        message = ChatMessage(role="user", content="Hello, AI!")

        assert message.role == "user"
        assert message.content == "Hello, AI!"

    def test_create_assistant_message(self):
        """Test creating an assistant message"""
        message = ChatMessage(role="assistant", content="Hello, human!")

        assert message.role == "assistant"
        assert message.content == "Hello, human!"

    def test_create_system_message(self):
        """Test creating a system message"""
        message = ChatMessage(role="system", content="You are a helpful assistant.")

        assert message.role == "system"
        assert message.content == "You are a helpful assistant."


class TestChatRequest:
    """Test ChatRequest model"""

    def test_create_basic_request(self):
        """Test creating a basic chat request"""
        messages = [
            ChatMessage(role="user", content="What is 2+2?"),
        ]
        request = ChatRequest(messages=messages, model="gpt-4")

        assert len(request.messages) == 1
        assert request.model == "gpt-4"
        assert request.temperature == 0.7  # default
        assert request.max_tokens is None
        assert request.stream is False

    def test_create_request_with_parameters(self):
        """Test creating a request with custom parameters"""
        messages = [
            ChatMessage(role="system", content="You are a math tutor."),
            ChatMessage(role="user", content="Explain calculus."),
        ]
        request = ChatRequest(
            messages=messages,
            model="gpt-4-turbo",
            temperature=0.5,
            max_tokens=1000,
            stream=True,
        )

        assert len(request.messages) == 2
        assert request.model == "gpt-4-turbo"
        assert request.temperature == 0.5
        assert request.max_tokens == 1000
        assert request.stream is True


class TestUsageInfo:
    """Test UsageInfo model"""

    def test_create_usage_info(self):
        """Test creating usage information"""
        usage = UsageInfo(input_tokens=100, output_tokens=200, total_tokens=300)

        assert usage.input_tokens == 100
        assert usage.output_tokens == 200
        assert usage.total_tokens == 300


class TestChatResponse:
    """Test ChatResponse model"""

    def test_create_response(self):
        """Test creating a chat response"""
        usage = UsageInfo(input_tokens=50, output_tokens=100, total_tokens=150)
        response = ChatResponse(
            content="The answer is 4.",
            usage=usage,
            model="gpt-4",
            finish_reason="stop",
        )

        assert response.content == "The answer is 4."
        assert response.role == "assistant"
        assert response.usage.total_tokens == 150
        assert response.model == "gpt-4"
        assert response.finish_reason == "stop"


class TestModelInfo:
    """Test ModelInfo model"""

    def test_create_model_info(self):
        """Test creating model information"""
        info = ModelInfo(
            provider="openai",
            model_name="gpt-4-turbo",
            context_window=128000,
            supports_streaming=True,
        )

        assert info.provider == "openai"
        assert info.model_name == "gpt-4-turbo"
        assert info.context_window == 128000
        assert info.supports_streaming is True


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing"""

    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """Mock chat completion"""
        return ChatResponse(
            content="Mock response",
            usage=UsageInfo(input_tokens=10, output_tokens=5, total_tokens=15),
            model=request.model,
            finish_reason="stop",
        )

    async def stream_completion(self, request: ChatRequest):
        """Mock stream completion"""
        for token in ["Mock", " ", "streaming", " ", "response"]:
            yield token

    def get_token_count(self, text: str) -> int:
        """Mock token count (approximate)"""
        return len(text.split())

    def get_model_info(self) -> ModelInfo:
        """Mock model info"""
        return ModelInfo(
            provider="mock",
            model_name="mock-model",
            context_window=8192,
            supports_streaming=True,
        )


class TestLLMProvider:
    """Test LLMProvider interface"""

    @pytest.mark.asyncio
    async def test_chat_completion(self):
        """Test chat completion method"""
        provider = MockLLMProvider()
        messages = [ChatMessage(role="user", content="Hello")]
        request = ChatRequest(messages=messages, model="mock-model")

        response = await provider.chat_completion(request)

        assert response.content == "Mock response"
        assert response.usage.total_tokens == 15
        assert response.model == "mock-model"

    @pytest.mark.asyncio
    async def test_stream_completion(self):
        """Test streaming completion"""
        provider = MockLLMProvider()
        messages = [ChatMessage(role="user", content="Hello")]
        request = ChatRequest(messages=messages, model="mock-model", stream=True)

        chunks = []
        async for chunk in provider.stream_completion(request):
            chunks.append(chunk)

        assert chunks == ["Mock", " ", "streaming", " ", "response"]

    def test_get_token_count(self):
        """Test token counting"""
        provider = MockLLMProvider()
        text = "This is a test message"

        count = provider.get_token_count(text)

        assert count == 5  # word count approximation

    def test_get_model_info(self):
        """Test getting model information"""
        provider = MockLLMProvider()

        info = provider.get_model_info()

        assert info.provider == "mock"
        assert info.model_name == "mock-model"
        assert info.context_window == 8192
        assert info.supports_streaming is True
