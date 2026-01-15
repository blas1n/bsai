"""Tests for WebSocket event handler."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.api.schemas import WSMessageType
from agent.events.handlers.websocket_handler import WebSocketEventHandler
from agent.events.types import (
    AgentActivityEvent,
    AgentStatus,
    BreakpointHitEvent,
    ContextCompressedEvent,
    Event,
    EventType,
    LLMChunkEvent,
    LLMCompleteEvent,
    MilestoneRetryEvent,
    MilestoneStatus,
    MilestoneStatusChangedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskProgressEvent,
    TaskStartedEvent,
)


@pytest.fixture
def mock_ws_manager() -> MagicMock:
    """Create a mock WebSocket manager."""
    manager = MagicMock()
    manager.broadcast_to_session = AsyncMock()
    return manager


@pytest.fixture
def handler(mock_ws_manager: MagicMock) -> WebSocketEventHandler:
    """Create a WebSocketEventHandler with mock manager."""
    return WebSocketEventHandler(mock_ws_manager)


class TestWebSocketEventHandlerInit:
    """Tests for WebSocketEventHandler initialization."""

    def test_init_with_ws_manager(self, mock_ws_manager: MagicMock) -> None:
        """Test handler initializes with ws_manager."""
        handler = WebSocketEventHandler(mock_ws_manager)
        assert handler.ws_manager is mock_ws_manager


class TestHandleMethod:
    """Tests for the main handle method."""

    async def test_handle_broadcasts_to_session(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test that handle broadcasts to the correct session."""
        session_id = uuid4()
        event = TaskStartedEvent(
            session_id=session_id,
            task_id=uuid4(),
            original_request="Test",
        )

        await handler.handle(event)

        mock_ws_manager.broadcast_to_session.assert_called_once()
        call_args = mock_ws_manager.broadcast_to_session.call_args
        assert call_args[0][0] == session_id

    async def test_handle_returns_none_for_unhandled_type(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test that unhandled event types don't broadcast."""

        # Create a custom event class that is not handled
        # Must inherit from Event directly, not a handled subclass
        class CustomEvent(Event):
            type: EventType = EventType.TASK_CANCELLED

        event = CustomEvent(
            session_id=uuid4(),
            task_id=uuid4(),
        )

        await handler.handle(event)

        # Should not broadcast for unhandled type
        mock_ws_manager.broadcast_to_session.assert_not_called()

    async def test_handle_catches_broadcast_errors(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test that broadcast errors are caught and logged."""
        mock_ws_manager.broadcast_to_session.side_effect = Exception("Network error")

        event = TaskStartedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
        )

        # Should not raise
        await handler.handle(event)


class TestTaskEventConversion:
    """Tests for task event to WS message conversion."""

    async def test_task_started_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test TaskStartedEvent conversion to WS message."""
        task_id = uuid4()
        session_id = uuid4()

        # previous_milestones must match PreviousMilestoneInfo schema
        event = TaskStartedEvent(
            session_id=session_id,
            task_id=task_id,
            original_request="Build feature",
            milestone_count=3,
            previous_milestones=[],  # Empty to avoid validation errors
            trace_url="https://trace.example.com/123",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.TASK_STARTED
        # payload is model_dump() result, UUIDs remain as UUID objects
        assert ws_message.payload["task_id"] == task_id
        assert ws_message.payload["session_id"] == session_id
        assert ws_message.payload["original_request"] == "Build feature"
        assert ws_message.payload["milestone_count"] == 3
        assert ws_message.payload["trace_url"] == "https://trace.example.com/123"

    async def test_task_progress_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test TaskProgressEvent conversion to WS message."""
        task_id = uuid4()

        event = TaskProgressEvent(
            session_id=uuid4(),
            task_id=task_id,
            current_milestone=2,
            total_milestones=5,
            progress=0.4,
            current_milestone_title="Implementing feature",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.TASK_PROGRESS
        # payload contains UUID objects from model_dump()
        assert ws_message.payload["task_id"] == task_id
        assert ws_message.payload["current_milestone"] == 2
        assert ws_message.payload["total_milestones"] == 5
        assert ws_message.payload["progress"] == 0.4

    async def test_task_completed_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test TaskCompletedEvent conversion to WS message."""
        task_id = uuid4()

        event = TaskCompletedEvent(
            session_id=uuid4(),
            task_id=task_id,
            final_result="Task completed",
            total_input_tokens=1000,
            total_output_tokens=500,
            total_cost_usd=Decimal("0.05"),
            duration_seconds=30.5,
            trace_url="https://trace.example.com/123",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.TASK_COMPLETED
        # payload contains UUID objects from model_dump()
        assert ws_message.payload["task_id"] == task_id
        assert ws_message.payload["final_result"] == "Task completed"
        assert ws_message.payload["total_tokens"] == 1500  # input + output
        assert ws_message.payload["duration_seconds"] == 30.5

    async def test_task_failed_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test TaskFailedEvent conversion to WS message."""
        task_id = uuid4()

        event = TaskFailedEvent(
            session_id=uuid4(),
            task_id=task_id,
            error="Something went wrong",
            failed_milestone=3,
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.TASK_FAILED
        # payload contains UUID objects from model_dump()
        assert ws_message.payload["task_id"] == task_id
        assert ws_message.payload["error"] == "Something went wrong"
        assert ws_message.payload["failed_milestone"] == 3


class TestAgentActivityConversion:
    """Tests for agent activity event conversion."""

    async def test_agent_started_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test AgentActivityEvent (started) conversion."""
        milestone_id = uuid4()

        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=milestone_id,
            sequence_number=2,
            agent="worker",
            status=AgentStatus.STARTED,
            message="Starting execution",
            details={"key": "value"},
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.MILESTONE_PROGRESS
        # UUID remains as UUID object in model_dump()
        assert ws_message.payload["milestone_id"] == milestone_id
        assert ws_message.payload["sequence_number"] == 2
        assert ws_message.payload["agent"] == "worker"
        # status is str(AgentStatus)
        assert str(ws_message.payload["status"]) == "started"
        assert ws_message.payload["message"] == "Starting execution"
        assert ws_message.payload["details"] == {"key": "value"}

    async def test_agent_completed_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test AgentActivityEvent (completed) conversion."""
        event = AgentActivityEvent(
            type=EventType.AGENT_COMPLETED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="qa",
            status=AgentStatus.COMPLETED,
            message="QA passed",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.MILESTONE_PROGRESS
        assert str(ws_message.payload["status"]) == "completed"

    async def test_agent_failed_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test AgentActivityEvent (failed) conversion."""
        event = AgentActivityEvent(
            type=EventType.AGENT_FAILED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.FAILED,
            message="Execution failed",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.MILESTONE_PROGRESS
        assert ws_message.payload["status"] == "failed"


class TestMilestoneEventConversion:
    """Tests for milestone event conversion."""

    async def test_milestone_status_changed_to_passed(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test MilestoneStatusChangedEvent (passed) uses MILESTONE_COMPLETED type."""
        event = MilestoneStatusChangedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            previous_status=MilestoneStatus.IN_PROGRESS,
            new_status=MilestoneStatus.PASSED,
            agent="qa",
            message="Milestone passed QA",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.MILESTONE_COMPLETED
        assert ws_message.payload["status"] == "passed"

    async def test_milestone_status_changed_to_failed(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test MilestoneStatusChangedEvent (failed) uses MILESTONE_FAILED type."""
        event = MilestoneStatusChangedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=2,
            previous_status=MilestoneStatus.IN_PROGRESS,
            new_status=MilestoneStatus.FAILED,
            agent="qa",
            message="Milestone failed QA",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.MILESTONE_FAILED
        assert ws_message.payload["status"] == "failed"

    async def test_milestone_status_changed_to_in_progress(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test MilestoneStatusChangedEvent (in_progress) uses MILESTONE_PROGRESS type."""
        event = MilestoneStatusChangedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            previous_status=MilestoneStatus.PENDING,
            new_status=MilestoneStatus.IN_PROGRESS,
            agent="worker",
            message="Starting milestone",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.MILESTONE_PROGRESS
        assert ws_message.payload["status"] == "in_progress"

    async def test_milestone_retry_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test MilestoneRetryEvent conversion."""
        event = MilestoneRetryEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=2,
            retry_count=2,
            max_retries=3,
            feedback="Fix the formatting",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.MILESTONE_RETRY
        assert ws_message.payload["status"] == "in_progress"
        assert "Retry 2/3" in ws_message.payload["message"]
        assert "Fix the formatting" in ws_message.payload["message"]


class TestLLMStreamingConversion:
    """Tests for LLM streaming event conversion."""

    async def test_llm_chunk_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test LLMChunkEvent conversion."""
        event = LLMChunkEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            chunk="Hello ",
            chunk_index=0,
            agent="worker",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.LLM_CHUNK
        assert ws_message.payload["chunk"] == "Hello "
        assert ws_message.payload["chunk_index"] == 0
        assert ws_message.payload["agent"] == "worker"

    async def test_llm_complete_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test LLMCompleteEvent conversion."""
        event = LLMCompleteEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            full_content="Hello world!",
            tokens_used=5,
            agent="worker",
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.LLM_COMPLETE
        assert ws_message.payload["full_content"] == "Hello world!"
        assert ws_message.payload["tokens_used"] == 5


class TestContextEventConversion:
    """Tests for context event conversion."""

    async def test_context_compressed_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test ContextCompressedEvent conversion."""
        task_id = uuid4()

        event = ContextCompressedEvent(
            session_id=uuid4(),
            task_id=task_id,
            old_message_count=100,
            new_message_count=10,
            tokens_saved_estimate=5000,
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.CONTEXT_COMPRESSED
        assert ws_message.payload["task_id"] == str(task_id)
        assert ws_message.payload["old_message_count"] == 100
        assert ws_message.payload["new_message_count"] == 10
        assert ws_message.payload["tokens_saved_estimate"] == 5000


class TestBreakpointEventConversion:
    """Tests for breakpoint event conversion."""

    async def test_breakpoint_hit_conversion(
        self, handler: WebSocketEventHandler, mock_ws_manager: MagicMock
    ) -> None:
        """Test BreakpointHitEvent conversion."""
        task_id = uuid4()
        session_id = uuid4()

        milestones = [
            {"description": "Setup", "status": "passed"},
            {"description": "Implement", "status": "in_progress"},
        ]

        event = BreakpointHitEvent(
            session_id=session_id,
            task_id=task_id,
            node_name="execute_worker",
            agent_type="worker",
            current_milestone_index=1,
            total_milestones=3,
            milestones=milestones,
            last_worker_output="Previous output",
            last_qa_result={"decision": "retry", "feedback": "Fix it"},
        )

        await handler.handle(event)

        call_args = mock_ws_manager.broadcast_to_session.call_args
        ws_message = call_args[0][1]

        assert ws_message.type == WSMessageType.BREAKPOINT_HIT
        # UUIDs remain as UUID objects in model_dump()
        assert ws_message.payload["task_id"] == task_id
        assert ws_message.payload["session_id"] == session_id
        assert ws_message.payload["node_name"] == "execute_worker"
        assert ws_message.payload["agent_type"] == "worker"
        assert ws_message.payload["current_state"]["current_milestone_index"] == 1
        assert ws_message.payload["current_state"]["total_milestones"] == 3
        assert ws_message.payload["current_state"]["milestones"] == milestones
        assert ws_message.payload["current_state"]["last_worker_output"] == "Previous output"
        assert ws_message.payload["current_state"]["last_qa_result"]["decision"] == "retry"


class TestToWsMessageMethod:
    """Tests for _to_ws_message internal method."""

    def test_unhandled_event_returns_none(self, handler: WebSocketEventHandler) -> None:
        """Test that unhandled event types return None."""
        # Create event with unhandled type
        from agent.events.types import Event

        class CustomEvent(Event):
            type: EventType = EventType.TASK_CANCELLED

        event = CustomEvent(
            session_id=uuid4(),
            task_id=uuid4(),
        )

        result = handler._to_ws_message(event)

        assert result is None

    def test_task_started_returns_ws_message(self, handler: WebSocketEventHandler) -> None:
        """Test that TaskStartedEvent returns valid WS message."""
        event = TaskStartedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
        )

        result = handler._to_ws_message(event)

        assert result is not None
        assert result.type == WSMessageType.TASK_STARTED
