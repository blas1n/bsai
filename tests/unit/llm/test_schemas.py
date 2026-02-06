"""LLM schema tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import ValidationError

from bsai.llm.schemas import ChatMessage, LLMRequest, LLMResponse, UsageInfo

if TYPE_CHECKING:
    pass


class TestChatMessage:
    """Tests for ChatMessage schema."""

    def test_valid_user_message(self) -> None:
        """Creates valid user message."""
        msg = ChatMessage(role="user", content="Hello!")
        assert msg.role == "user"
        assert msg.content == "Hello!"

    def test_valid_system_message(self) -> None:
        """Creates valid system message."""
        msg = ChatMessage(role="system", content="You are helpful.")
        assert msg.role == "system"

    def test_valid_assistant_message(self) -> None:
        """Creates valid assistant message."""
        msg = ChatMessage(role="assistant", content="I can help!")
        assert msg.role == "assistant"

    def test_invalid_role_raises_error(self) -> None:
        """Raises error for invalid role."""
        with pytest.raises(ValidationError):
            ChatMessage(role=cast(Any, "invalid"), content="Test")

    def test_empty_content_allowed(self) -> None:
        """Allows empty content."""
        msg = ChatMessage(role="user", content="")
        assert msg.content == ""


class TestLLMRequest:
    """Tests for LLMRequest schema."""

    def test_minimal_request(self) -> None:
        """Creates request with minimal fields."""
        request = LLMRequest(
            model="gpt-4",
            messages=[ChatMessage(role="user", content="Hi")],
        )
        assert request.model == "gpt-4"
        assert len(request.messages) == 1
        assert request.temperature == 0.7  # Default
        assert request.max_tokens is None
        assert request.stream is False

    def test_full_request(self) -> None:
        """Creates request with all fields."""
        request = LLMRequest(
            model="claude-3-opus",
            messages=[
                ChatMessage(role="system", content="Be helpful"),
                ChatMessage(role="user", content="Hello"),
            ],
            temperature=0.5,
            max_tokens=1000,
            stream=True,
            api_base="https://custom.api.com",
            api_key="sk-test-key",
        )
        assert request.temperature == 0.5
        assert request.max_tokens == 1000
        assert request.stream is True
        assert request.api_base == "https://custom.api.com"
        assert request.api_key == "sk-test-key"

    def test_temperature_bounds(self) -> None:
        """Enforces temperature bounds."""
        # Valid at 0
        request = LLMRequest(
            model="gpt-4",
            messages=[ChatMessage(role="user", content="Hi")],
            temperature=0.0,
        )
        assert request.temperature == 0.0

        # Valid at 2
        request = LLMRequest(
            model="gpt-4",
            messages=[ChatMessage(role="user", content="Hi")],
            temperature=2.0,
        )
        assert request.temperature == 2.0

        # Invalid below 0
        with pytest.raises(ValidationError):
            LLMRequest(
                model="gpt-4",
                messages=[ChatMessage(role="user", content="Hi")],
                temperature=-0.1,
            )

        # Invalid above 2
        with pytest.raises(ValidationError):
            LLMRequest(
                model="gpt-4",
                messages=[ChatMessage(role="user", content="Hi")],
                temperature=2.1,
            )

    def test_empty_messages_allowed(self) -> None:
        """Allows empty messages list."""
        request = LLMRequest(model="gpt-4", messages=[])
        assert request.messages == []


class TestUsageInfo:
    """Tests for UsageInfo schema."""

    def test_valid_usage(self) -> None:
        """Creates valid usage info."""
        usage = UsageInfo(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150

    def test_zero_tokens_allowed(self) -> None:
        """Allows zero tokens."""
        usage = UsageInfo(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        )
        assert usage.input_tokens == 0

    def test_negative_tokens_rejected(self) -> None:
        """Rejects negative token counts."""
        with pytest.raises(ValidationError):
            UsageInfo(
                input_tokens=-1,
                output_tokens=50,
                total_tokens=49,
            )

        with pytest.raises(ValidationError):
            UsageInfo(
                input_tokens=100,
                output_tokens=-1,
                total_tokens=99,
            )


class TestLLMResponse:
    """Tests for LLMResponse schema."""

    def test_valid_response(self) -> None:
        """Creates valid response."""
        response = LLMResponse(
            content="Hello! How can I help?",
            usage=UsageInfo(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
            ),
            model="gpt-4-turbo",
            finish_reason="stop",
        )
        assert response.content == "Hello! How can I help?"
        assert response.model == "gpt-4-turbo"
        assert response.finish_reason == "stop"

    def test_none_finish_reason(self) -> None:
        """Allows None finish_reason."""
        response = LLMResponse(
            content="Partial response",
            usage=UsageInfo(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
            ),
            model="gpt-4",
            finish_reason=None,
        )
        assert response.finish_reason is None

    def test_empty_content_allowed(self) -> None:
        """Allows empty content."""
        response = LLMResponse(
            content="",
            usage=UsageInfo(
                input_tokens=10,
                output_tokens=0,
                total_tokens=10,
            ),
            model="gpt-4",
        )
        assert response.content == ""
