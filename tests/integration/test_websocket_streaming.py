"""Integration tests for WebSocket streaming."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest

from agent.api.schemas.websocket import (
    LLMChunkPayload,
    LLMCompletePayload,
    MilestoneProgressPayload,
    TaskCompletedPayload,
    TaskFailedPayload,
    TaskProgressPayload,
    TaskStartedPayload,
    WSMessage,
    WSMessageType,
)
from agent.db.models.enums import MilestoneStatus


class TestWSMessageTypes:
    """Tests for WebSocket message type enumeration."""

    def test_client_to_server_types(self):
        """Test client-to-server message types."""
        client_types = [
            WSMessageType.AUTH,
            WSMessageType.SUBSCRIBE,
            WSMessageType.UNSUBSCRIBE,
            WSMessageType.PING,
        ]
        for msg_type in client_types:
            assert msg_type.value in ["auth", "subscribe", "unsubscribe", "ping"]

    def test_server_to_client_auth_types(self):
        """Test server-to-client auth message types."""
        auth_types = [
            WSMessageType.AUTH_SUCCESS,
            WSMessageType.AUTH_ERROR,
            WSMessageType.SUBSCRIBED,
            WSMessageType.UNSUBSCRIBED,
            WSMessageType.PONG,
        ]
        for msg_type in auth_types:
            assert msg_type is not None

    def test_task_event_types(self):
        """Test task event message types."""
        task_types = [
            WSMessageType.TASK_STARTED,
            WSMessageType.TASK_PROGRESS,
            WSMessageType.TASK_COMPLETED,
            WSMessageType.TASK_FAILED,
        ]
        for msg_type in task_types:
            assert msg_type.value.startswith("task_")

    def test_milestone_event_types(self):
        """Test milestone event message types."""
        milestone_types = [
            WSMessageType.MILESTONE_STARTED,
            WSMessageType.MILESTONE_PROGRESS,
            WSMessageType.MILESTONE_COMPLETED,
            WSMessageType.MILESTONE_FAILED,
            WSMessageType.MILESTONE_RETRY,
        ]
        for msg_type in milestone_types:
            assert msg_type.value.startswith("milestone_")

    def test_llm_streaming_types(self):
        """Test LLM streaming message types."""
        llm_types = [
            WSMessageType.LLM_CHUNK,
            WSMessageType.LLM_COMPLETE,
        ]
        for msg_type in llm_types:
            assert msg_type.value.startswith("llm_")


class TestWSMessage:
    """Tests for WSMessage envelope."""

    def test_message_creation(self):
        """Test creating a WebSocket message."""
        message = WSMessage(
            type=WSMessageType.TASK_STARTED,
            payload={"task_id": str(uuid4())},
        )
        assert message.type == WSMessageType.TASK_STARTED
        assert message.timestamp is not None
        assert message.request_id is None

    def test_message_with_request_id(self):
        """Test message with request ID."""
        request_id = "req-123"
        message = WSMessage(
            type=WSMessageType.PONG,
            payload={},
            request_id=request_id,
        )
        assert message.request_id == request_id

    def test_message_serialization(self):
        """Test message serialization to JSON."""
        message = WSMessage(
            type=WSMessageType.AUTH_SUCCESS,
            payload={"user_id": "test-user"},
        )
        json_data = message.model_dump_json()
        parsed = json.loads(json_data)

        assert parsed["type"] == "auth_success"
        assert parsed["payload"]["user_id"] == "test-user"
        assert "timestamp" in parsed


class TestTaskPayloads:
    """Tests for task event payloads."""

    def test_task_started_payload(self):
        """Test TaskStartedPayload creation."""
        task_id = uuid4()
        session_id = uuid4()
        payload = TaskStartedPayload(
            task_id=task_id,
            session_id=session_id,
            original_request="Test task",
            milestone_count=3,
        )
        assert payload.task_id == task_id
        assert payload.milestone_count == 3

    def test_task_progress_payload(self):
        """Test TaskProgressPayload creation."""
        task_id = uuid4()
        payload = TaskProgressPayload(
            task_id=task_id,
            current_milestone=2,
            total_milestones=5,
            progress=0.4,
            current_milestone_title="Processing data",
        )
        assert payload.progress == 0.4
        assert payload.current_milestone == 2

    def test_task_progress_validation(self):
        """Test TaskProgressPayload validation."""
        with pytest.raises(ValueError):
            TaskProgressPayload(
                task_id=uuid4(),
                current_milestone=1,
                total_milestones=3,
                progress=1.5,  # Invalid: > 1.0
                current_milestone_title="Invalid",
            )

    def test_task_completed_payload(self):
        """Test TaskCompletedPayload creation."""
        task_id = uuid4()
        payload = TaskCompletedPayload(
            task_id=task_id,
            final_result="Task completed successfully",
            total_tokens=1500,
            total_cost_usd=Decimal("0.025"),
            duration_seconds=45.5,
        )
        assert payload.total_tokens == 1500
        assert payload.total_cost_usd == Decimal("0.025")

    def test_task_failed_payload(self):
        """Test TaskFailedPayload creation."""
        task_id = uuid4()
        payload = TaskFailedPayload(
            task_id=task_id,
            error="API rate limit exceeded",
            failed_milestone=2,
        )
        assert payload.error == "API rate limit exceeded"
        assert payload.failed_milestone == 2

    def test_task_failed_without_milestone(self):
        """Test TaskFailedPayload without specific milestone."""
        payload = TaskFailedPayload(
            task_id=uuid4(),
            error="General failure",
        )
        assert payload.failed_milestone is None


class TestMilestonePayloads:
    """Tests for milestone event payloads."""

    def test_milestone_progress_payload(self):
        """Test MilestoneProgressPayload creation."""
        milestone_id = uuid4()
        task_id = uuid4()
        payload = MilestoneProgressPayload(
            milestone_id=milestone_id,
            task_id=task_id,
            sequence_number=1,
            status=MilestoneStatus.IN_PROGRESS,
            agent="worker",
            message="Processing milestone",
        )
        assert payload.status == MilestoneStatus.IN_PROGRESS
        assert payload.agent == "worker"

    def test_milestone_progress_all_statuses(self):
        """Test all milestone statuses are valid."""
        statuses = [
            MilestoneStatus.PENDING,
            MilestoneStatus.IN_PROGRESS,
            MilestoneStatus.PASSED,
            MilestoneStatus.FAILED,
        ]
        for status in statuses:
            payload = MilestoneProgressPayload(
                milestone_id=uuid4(),
                task_id=uuid4(),
                sequence_number=1,
                status=status,
                agent="qa",
                message=f"Status: {status}",
            )
            assert payload.status == status


class TestLLMStreamingPayloads:
    """Tests for LLM streaming payloads."""

    def test_llm_chunk_payload(self):
        """Test LLMChunkPayload creation."""
        task_id = uuid4()
        milestone_id = uuid4()
        payload = LLMChunkPayload(
            task_id=task_id,
            milestone_id=milestone_id,
            chunk="Hello, ",
            chunk_index=0,
            agent="worker",
        )
        assert payload.chunk == "Hello, "
        assert payload.chunk_index == 0

    def test_llm_chunk_sequence(self):
        """Test sequence of LLM chunks."""
        task_id = uuid4()
        milestone_id = uuid4()
        chunks = ["Hello", ", ", "World", "!"]

        payloads = [
            LLMChunkPayload(
                task_id=task_id,
                milestone_id=milestone_id,
                chunk=chunk,
                chunk_index=i,
                agent="worker",
            )
            for i, chunk in enumerate(chunks)
        ]

        assert len(payloads) == 4
        assert all(p.task_id == task_id for p in payloads)
        assert [p.chunk for p in payloads] == chunks

    def test_llm_complete_payload(self):
        """Test LLMCompletePayload creation."""
        task_id = uuid4()
        milestone_id = uuid4()
        payload = LLMCompletePayload(
            task_id=task_id,
            milestone_id=milestone_id,
            full_content="Complete response content",
            tokens_used=150,
            agent="meta_prompter",
        )
        assert payload.full_content == "Complete response content"
        assert payload.tokens_used == 150
        assert payload.agent == "meta_prompter"


class TestWebSocketMessageFlow:
    """Tests for WebSocket message flow patterns."""

    def test_auth_flow_messages(self):
        """Test authentication message flow."""
        # Client sends auth
        auth_request = WSMessage(
            type=WSMessageType.AUTH,
            payload={"token": "jwt-token-here"},
        )
        assert auth_request.type == WSMessageType.AUTH

        # Server responds with success
        auth_success = WSMessage(
            type=WSMessageType.AUTH_SUCCESS,
            payload={"user_id": "user-123"},
        )
        assert auth_success.type == WSMessageType.AUTH_SUCCESS

    def test_subscription_flow_messages(self):
        """Test subscription message flow."""
        session_id = str(uuid4())

        # Client subscribes
        subscribe = WSMessage(
            type=WSMessageType.SUBSCRIBE,
            payload={"session_id": session_id},
        )
        assert subscribe.type == WSMessageType.SUBSCRIBE

        # Server confirms
        subscribed = WSMessage(
            type=WSMessageType.SUBSCRIBED,
            payload={"session_id": session_id},
        )
        assert subscribed.type == WSMessageType.SUBSCRIBED

    def test_task_lifecycle_messages(self):
        """Test complete task lifecycle message sequence."""
        task_id = uuid4()
        session_id = uuid4()

        # Task started
        started = WSMessage(
            type=WSMessageType.TASK_STARTED,
            payload=TaskStartedPayload(
                task_id=task_id,
                session_id=session_id,
                original_request="Test",
                milestone_count=2,
            ).model_dump(),
        )
        assert started.type == WSMessageType.TASK_STARTED

        # Task progress
        progress = WSMessage(
            type=WSMessageType.TASK_PROGRESS,
            payload=TaskProgressPayload(
                task_id=task_id,
                current_milestone=1,
                total_milestones=2,
                progress=0.5,
                current_milestone_title="Step 1",
            ).model_dump(),
        )
        assert progress.type == WSMessageType.TASK_PROGRESS

        # Task completed
        completed = WSMessage(
            type=WSMessageType.TASK_COMPLETED,
            payload=TaskCompletedPayload(
                task_id=task_id,
                final_result="Done",
                total_tokens=500,
                total_cost_usd=Decimal("0.01"),
                duration_seconds=10.0,
            ).model_dump(),
        )
        assert completed.type == WSMessageType.TASK_COMPLETED

    def test_ping_pong_messages(self):
        """Test keepalive ping/pong messages."""
        ping = WSMessage(
            type=WSMessageType.PING,
            payload={},
            request_id="ping-1",
        )
        assert ping.type == WSMessageType.PING

        pong = WSMessage(
            type=WSMessageType.PONG,
            payload={},
            request_id="ping-1",
        )
        assert pong.type == WSMessageType.PONG
        assert pong.request_id == ping.request_id

    def test_error_message(self):
        """Test error message."""
        error = WSMessage(
            type=WSMessageType.ERROR,
            payload={"code": "INVALID_SESSION", "message": "Session not found"},
        )
        assert error.type == WSMessageType.ERROR
        assert "code" in error.payload
