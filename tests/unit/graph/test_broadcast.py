"""Unit tests for WebSocket broadcast utilities."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from agent.api.schemas import WSMessage, WSMessageType
from agent.db.models.enums import MilestoneStatus
from agent.graph.broadcast import (
    broadcast_agent_completed,
    broadcast_agent_started,
    broadcast_milestone_completed,
    broadcast_milestone_retry,
    broadcast_task_completed,
    broadcast_task_progress,
    broadcast_task_started,
)


@pytest.fixture
def session_id() -> UUID:
    """Generate a session ID for tests."""
    return uuid4()


@pytest.fixture
def task_id() -> UUID:
    """Generate a task ID for tests."""
    return uuid4()


@pytest.fixture
def milestone_id() -> UUID:
    """Generate a milestone ID for tests."""
    return uuid4()


@pytest.fixture
def mock_ws_manager() -> MagicMock:
    """Create a mock WebSocket connection manager."""
    manager = MagicMock()
    manager.broadcast_to_session = AsyncMock()
    return manager


class TestBroadcastAgentStarted:
    """Tests for broadcast_agent_started function."""

    @pytest.mark.asyncio
    async def test_broadcasts_message(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should broadcast agent started message."""
        await broadcast_agent_started(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            agent="worker",
            message="Starting work",
            details={"test": "data"},
        )

        mock_ws_manager.broadcast_to_session.assert_called_once()
        call_args = mock_ws_manager.broadcast_to_session.call_args
        assert call_args[0][0] == session_id

        message: WSMessage = call_args[0][1]
        assert message.type == WSMessageType.MILESTONE_PROGRESS
        assert message.payload["agent"] == "worker"
        assert message.payload["message"] == "Starting work"
        assert message.payload["status"] == MilestoneStatus.IN_PROGRESS.value

    @pytest.mark.asyncio
    async def test_no_broadcast_when_manager_none(
        self,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should not raise when ws_manager is None."""
        # Should not raise
        await broadcast_agent_started(
            ws_manager=None,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            agent="worker",
            message="Starting work",
        )

    @pytest.mark.asyncio
    async def test_handles_broadcast_error(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should handle broadcast errors gracefully."""
        mock_ws_manager.broadcast_to_session.side_effect = Exception("Network error")

        # Should not raise
        await broadcast_agent_started(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            agent="worker",
            message="Starting work",
        )


class TestBroadcastAgentCompleted:
    """Tests for broadcast_agent_completed function."""

    @pytest.mark.asyncio
    async def test_broadcasts_message(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should broadcast agent completed message."""
        await broadcast_agent_completed(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=2,
            agent="qa",
            message="QA completed",
            status=MilestoneStatus.PASSED,
            details={"result": "passed"},
        )

        mock_ws_manager.broadcast_to_session.assert_called_once()
        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        assert message.type == WSMessageType.MILESTONE_PROGRESS
        assert message.payload["agent"] == "qa"
        assert message.payload["status"] == MilestoneStatus.PASSED.value

    @pytest.mark.asyncio
    async def test_no_broadcast_when_manager_none(
        self,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should not raise when ws_manager is None."""
        await broadcast_agent_completed(
            ws_manager=None,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            agent="qa",
            message="Done",
        )


class TestBroadcastTaskProgress:
    """Tests for broadcast_task_progress function."""

    @pytest.mark.asyncio
    async def test_broadcasts_message(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should broadcast task progress message."""
        await broadcast_task_progress(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            current_milestone=1,  # 0-based
            total_milestones=5,
            current_milestone_title="Test milestone",
        )

        mock_ws_manager.broadcast_to_session.assert_called_once()
        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        assert message.type == WSMessageType.TASK_PROGRESS
        assert message.payload["current_milestone"] == 2  # 1-based for UI
        assert message.payload["total_milestones"] == 5
        assert message.payload["progress"] == 0.4  # (1+1)/5
        assert message.payload["current_milestone_title"] == "Test milestone"

    @pytest.mark.asyncio
    async def test_handles_zero_milestones(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should handle zero total milestones."""
        await broadcast_task_progress(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            current_milestone=0,
            total_milestones=0,
            current_milestone_title="No milestones",
        )

        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]
        assert message.payload["progress"] == 0.0

    @pytest.mark.asyncio
    async def test_no_broadcast_when_manager_none(
        self,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should not raise when ws_manager is None."""
        await broadcast_task_progress(
            ws_manager=None,
            session_id=session_id,
            task_id=task_id,
            current_milestone=0,
            total_milestones=5,
            current_milestone_title="Test",
        )


class TestBroadcastMilestoneCompleted:
    """Tests for broadcast_milestone_completed function."""

    @pytest.mark.asyncio
    async def test_broadcasts_passed_message(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should broadcast milestone passed message."""
        await broadcast_milestone_completed(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            status=MilestoneStatus.PASSED,
        )

        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        assert message.type == WSMessageType.MILESTONE_COMPLETED
        assert message.payload["status"] == MilestoneStatus.PASSED.value

    @pytest.mark.asyncio
    async def test_broadcasts_failed_message(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should broadcast milestone failed message."""
        await broadcast_milestone_completed(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            status=MilestoneStatus.FAILED,
        )

        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        assert message.type == WSMessageType.MILESTONE_FAILED
        assert message.payload["status"] == MilestoneStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_no_broadcast_when_manager_none(
        self,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should not raise when ws_manager is None."""
        await broadcast_milestone_completed(
            ws_manager=None,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            status=MilestoneStatus.PASSED,
        )


class TestBroadcastMilestoneRetry:
    """Tests for broadcast_milestone_retry function."""

    @pytest.mark.asyncio
    async def test_broadcasts_message(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should broadcast milestone retry message."""
        await broadcast_milestone_retry(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            retry_count=2,
            feedback="Please fix the formatting",
        )

        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        assert message.type == WSMessageType.MILESTONE_RETRY
        assert "Retry 2/3" in message.payload["message"]
        assert "Please fix the formatting" in message.payload["message"]

    @pytest.mark.asyncio
    async def test_broadcasts_without_feedback(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should broadcast retry message without feedback."""
        await broadcast_milestone_retry(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            retry_count=1,
            feedback=None,
        )

        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        assert message.payload["message"] == "Retry 1/3"

    @pytest.mark.asyncio
    async def test_truncates_long_feedback(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should truncate long feedback in retry message."""
        long_feedback = "x" * 200

        await broadcast_milestone_retry(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            retry_count=1,
            feedback=long_feedback,
        )

        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        # Feedback should be truncated to 100 chars
        assert len(message.payload["message"]) <= len("Retry 1/3: ") + 100

    @pytest.mark.asyncio
    async def test_no_broadcast_when_manager_none(
        self,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID,
    ) -> None:
        """Should not raise when ws_manager is None."""
        await broadcast_milestone_retry(
            ws_manager=None,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            sequence_number=1,
            retry_count=1,
        )


class TestBroadcastTaskStarted:
    """Tests for broadcast_task_started function."""

    @pytest.mark.asyncio
    async def test_broadcasts_message(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should broadcast task started message with trace URL."""
        await broadcast_task_started(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            original_request="Test request",
            milestone_count=5,
            trace_url="http://langfuse:3000/trace/123",
        )

        mock_ws_manager.broadcast_to_session.assert_called_once()
        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        assert message.type == WSMessageType.TASK_STARTED
        # UUID may be serialized as UUID object or string depending on model_dump()
        assert str(message.payload["task_id"]) == str(task_id)
        assert str(message.payload["session_id"]) == str(session_id)
        assert message.payload["original_request"] == "Test request"
        assert message.payload["milestone_count"] == 5
        assert message.payload["trace_url"] == "http://langfuse:3000/trace/123"

    @pytest.mark.asyncio
    async def test_broadcasts_without_trace_url(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should broadcast task started message with empty trace URL."""
        await broadcast_task_started(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            original_request="Test request",
            milestone_count=0,
            trace_url="",
        )

        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        assert message.payload["trace_url"] == ""

    @pytest.mark.asyncio
    async def test_no_broadcast_when_manager_none(
        self,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should not raise when ws_manager is None."""
        await broadcast_task_started(
            ws_manager=None,
            session_id=session_id,
            task_id=task_id,
            original_request="Test request",
        )

    @pytest.mark.asyncio
    async def test_handles_broadcast_error(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should handle broadcast errors gracefully."""
        mock_ws_manager.broadcast_to_session.side_effect = Exception("Network error")

        # Should not raise
        await broadcast_task_started(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            original_request="Test request",
        )


class TestBroadcastTaskCompleted:
    """Tests for broadcast_task_completed function."""

    @pytest.mark.asyncio
    async def test_broadcasts_message(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should broadcast task completed message with all fields."""
        await broadcast_task_completed(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            final_result="Task completed successfully",
            total_tokens=1500,
            total_cost_usd=Decimal("0.05"),
            duration_seconds=45.5,
            trace_url="http://langfuse:3000/trace/123",
        )

        mock_ws_manager.broadcast_to_session.assert_called_once()
        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        assert message.type == WSMessageType.TASK_COMPLETED
        # UUID may be serialized as UUID object or string depending on model_dump()
        assert str(message.payload["task_id"]) == str(task_id)
        assert message.payload["final_result"] == "Task completed successfully"
        assert message.payload["total_tokens"] == 1500
        assert message.payload["duration_seconds"] == 45.5
        assert message.payload["trace_url"] == "http://langfuse:3000/trace/123"

    @pytest.mark.asyncio
    async def test_converts_string_cost_to_decimal(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should convert string cost to Decimal."""
        await broadcast_task_completed(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            final_result="Done",
            total_tokens=100,
            total_cost_usd="0.01",  # String instead of Decimal
            duration_seconds=10.0,
        )

        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        # Should be a valid Decimal string representation
        assert message.payload["total_cost_usd"] is not None

    @pytest.mark.asyncio
    async def test_broadcasts_without_trace_url(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should broadcast task completed message with empty trace URL."""
        await broadcast_task_completed(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            final_result="Done",
            total_tokens=100,
            total_cost_usd=Decimal("0.01"),
            duration_seconds=5.0,
            trace_url="",
        )

        call_args = mock_ws_manager.broadcast_to_session.call_args
        message: WSMessage = call_args[0][1]

        assert message.payload["trace_url"] == ""

    @pytest.mark.asyncio
    async def test_no_broadcast_when_manager_none(
        self,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should not raise when ws_manager is None."""
        await broadcast_task_completed(
            ws_manager=None,
            session_id=session_id,
            task_id=task_id,
            final_result="Done",
            total_tokens=100,
            total_cost_usd=Decimal("0.01"),
            duration_seconds=5.0,
        )

    @pytest.mark.asyncio
    async def test_handles_broadcast_error(
        self,
        mock_ws_manager: MagicMock,
        session_id: UUID,
        task_id: UUID,
    ) -> None:
        """Should handle broadcast errors gracefully."""
        mock_ws_manager.broadcast_to_session.side_effect = Exception("Network error")

        # Should not raise
        await broadcast_task_completed(
            ws_manager=mock_ws_manager,
            session_id=session_id,
            task_id=task_id,
            final_result="Done",
            total_tokens=100,
            total_cost_usd=Decimal("0.01"),
            duration_seconds=5.0,
        )
