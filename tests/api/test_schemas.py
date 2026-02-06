"""Schema validation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from bsai.api.schemas import (
    SessionCreate,
    SessionResponse,
    TaskCreate,
    WSMessage,
    WSMessageType,
)
from bsai.db.models.enums import SessionStatus


class TestSessionSchemas:
    """Session schema tests."""

    def test_session_create_minimal(self) -> None:
        """Session can be created with no metadata."""
        session = SessionCreate()
        assert session.metadata is None

    def test_session_create_with_metadata(self) -> None:
        """Session can be created with metadata."""
        metadata = {"project": "test", "version": 1}
        session = SessionCreate(metadata=metadata)
        assert session.metadata == metadata

    def test_session_response_validation(self) -> None:
        """SessionResponse validates correctly."""
        now = datetime.now(UTC)
        response = SessionResponse(
            id=uuid4(),
            user_id="user-123",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        assert response.status == "active"


class TestTaskSchemas:
    """Task schema tests."""

    def test_task_create_minimal(self) -> None:
        """Task can be created with just request."""
        task = TaskCreate(original_request="Implement feature X")
        assert task.original_request == "Implement feature X"
        assert task.max_context_tokens == 100000
        assert task.stream is True

    def test_task_create_custom_tokens(self) -> None:
        """Task can have custom token limit."""
        task = TaskCreate(
            original_request="Test",
            max_context_tokens=50000,
            stream=False,
        )
        assert task.max_context_tokens == 50000
        assert task.stream is False

    def test_task_create_empty_request_fails(self) -> None:
        """Task creation fails with empty request."""
        with pytest.raises(ValidationError):
            TaskCreate(original_request="")

    def test_task_create_tokens_too_low_fails(self) -> None:
        """Task creation fails with tokens below minimum."""
        with pytest.raises(ValidationError):
            TaskCreate(original_request="Test", max_context_tokens=100)

    def test_task_create_tokens_too_high_fails(self) -> None:
        """Task creation fails with tokens above maximum."""
        with pytest.raises(ValidationError):
            TaskCreate(original_request="Test", max_context_tokens=500000)


class TestWebSocketSchemas:
    """WebSocket schema tests."""

    def test_ws_message_types_exist(self) -> None:
        """All expected message types exist."""
        assert WSMessageType.AUTH == "auth"
        assert WSMessageType.TASK_STARTED == "task_started"
        assert WSMessageType.LLM_CHUNK == "llm_chunk"
        assert WSMessageType.ERROR == "error"

    def test_ws_message_with_payload(self) -> None:
        """WSMessage can have payload."""
        message = WSMessage(
            type=WSMessageType.TASK_STARTED,
            payload={"task_id": str(uuid4())},
        )
        assert message.type == WSMessageType.TASK_STARTED
        assert "task_id" in message.payload

    def test_ws_message_default_payload(self) -> None:
        """WSMessage defaults to empty payload."""
        message = WSMessage(type=WSMessageType.PONG)
        assert message.payload == {}
        assert message.timestamp is not None
