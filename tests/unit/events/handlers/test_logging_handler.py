"""Tests for Logging event handler."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from agent.events.handlers.logging_handler import LoggingEventHandler
from agent.events.types import (
    AgentActivityEvent,
    AgentStatus,
    ContextCompressedEvent,
    EventType,
    LLMChunkEvent,
    MilestoneRetryEvent,
    MilestoneStatus,
    MilestoneStatusChangedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskStartedEvent,
)


@pytest.fixture
def handler() -> LoggingEventHandler:
    """Create a LoggingEventHandler."""
    return LoggingEventHandler()


@pytest.fixture
def handler_info_level() -> LoggingEventHandler:
    """Create a LoggingEventHandler with info log level."""
    return LoggingEventHandler(log_level="info")


class TestLogLevelDetermination:
    """Tests for _get_log_level method."""

    def test_error_level_for_task_failed(self, handler: LoggingEventHandler) -> None:
        """Test that TASK_FAILED uses error level."""
        level = handler._get_log_level(EventType.TASK_FAILED)
        assert level == "error"

    def test_error_level_for_milestone_failed(self, handler: LoggingEventHandler) -> None:
        """Test that MILESTONE_FAILED uses error level."""
        level = handler._get_log_level(EventType.MILESTONE_FAILED)
        assert level == "error"

    def test_error_level_for_agent_failed(self, handler: LoggingEventHandler) -> None:
        """Test that AGENT_FAILED uses error level."""
        level = handler._get_log_level(EventType.AGENT_FAILED)
        assert level == "error"

    def test_info_level_for_task_completed(self, handler: LoggingEventHandler) -> None:
        """Test that TASK_COMPLETED uses info level."""
        level = handler._get_log_level(EventType.TASK_COMPLETED)
        assert level == "info"

    def test_info_level_for_milestone_completed(self, handler: LoggingEventHandler) -> None:
        """Test that MILESTONE_COMPLETED uses info level."""
        level = handler._get_log_level(EventType.MILESTONE_COMPLETED)
        assert level == "info"

    def test_warning_level_for_milestone_retry(self, handler: LoggingEventHandler) -> None:
        """Test that MILESTONE_RETRY uses warning level."""
        level = handler._get_log_level(EventType.MILESTONE_RETRY)
        assert level == "warning"

    def test_default_level_for_other_events(self, handler: LoggingEventHandler) -> None:
        """Test that other events use default level."""
        level = handler._get_log_level(EventType.TASK_STARTED)
        assert level == "debug"

        level = handler._get_log_level(EventType.AGENT_STARTED)
        assert level == "debug"

        level = handler._get_log_level(EventType.LLM_CHUNK)
        assert level == "debug"

    def test_custom_default_level(self, handler_info_level: LoggingEventHandler) -> None:
        """Test that custom default level is used."""
        level = handler_info_level._get_log_level(EventType.TASK_STARTED)
        assert level == "info"


class TestExtraFieldExtraction:
    """Tests for _extract_extra_fields method."""

    def test_extracts_milestone_id(self, handler: LoggingEventHandler) -> None:
        """Test extraction of milestone_id field."""
        milestone_id = uuid4()
        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=milestone_id,
            sequence_number=1,
            agent="worker",
            status=AgentStatus.STARTED,
            message="Starting",
        )

        extra = handler._extract_extra_fields(event)

        assert extra["milestone_id"] == str(milestone_id)

    def test_extracts_sequence_number(self, handler: LoggingEventHandler) -> None:
        """Test extraction of sequence_number field."""
        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=5,
            agent="worker",
            status=AgentStatus.STARTED,
            message="Starting",
        )

        extra = handler._extract_extra_fields(event)

        assert extra["sequence_number"] == 5

    def test_extracts_agent(self, handler: LoggingEventHandler) -> None:
        """Test extraction of agent field."""
        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="conductor",
            status=AgentStatus.STARTED,
            message="Starting",
        )

        extra = handler._extract_extra_fields(event)

        assert extra["agent"] == "conductor"

    def test_extracts_status(self, handler: LoggingEventHandler) -> None:
        """Test extraction of status field."""
        event = AgentActivityEvent(
            type=EventType.AGENT_COMPLETED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.COMPLETED,
            message="Done",
        )

        extra = handler._extract_extra_fields(event)

        assert extra["status"] == "completed"

    def test_extracts_message(self, handler: LoggingEventHandler) -> None:
        """Test extraction of message field."""
        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.STARTED,
            message="Starting execution",
        )

        extra = handler._extract_extra_fields(event)

        assert extra["message"] == "Starting execution"

    def test_truncates_long_message(self, handler: LoggingEventHandler) -> None:
        """Test that long messages are truncated to 200 chars."""
        long_message = "x" * 500
        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.STARTED,
            message=long_message,
        )

        extra = handler._extract_extra_fields(event)

        assert len(extra["message"]) == 200

    def test_extracts_error(self, handler: LoggingEventHandler) -> None:
        """Test extraction of error field."""
        event = TaskFailedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            error="Something went wrong",
        )

        extra = handler._extract_extra_fields(event)

        assert extra["error"] == "Something went wrong"

    def test_no_extra_fields_for_minimal_event(self, handler: LoggingEventHandler) -> None:
        """Test that minimal events have no extra fields."""
        event = TaskStartedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
        )

        extra = handler._extract_extra_fields(event)

        # TaskStartedEvent doesn't have milestone_id, sequence_number, etc.
        assert "milestone_id" not in extra
        assert "sequence_number" not in extra


class TestHandleMethod:
    """Tests for the main handle method."""

    @patch("agent.events.handlers.logging_handler.logger")
    async def test_logs_with_correct_data(self, mock_logger, handler: LoggingEventHandler) -> None:
        """Test that handle logs with correct structured data."""
        session_id = uuid4()
        task_id = uuid4()

        event = TaskStartedEvent(
            session_id=session_id,
            task_id=task_id,
            original_request="Test request",
        )

        await handler.handle(event)

        mock_logger.debug.assert_called_once()
        call_kwargs = mock_logger.debug.call_args[1]

        assert call_kwargs["event_type"] == "task.started"
        assert call_kwargs["session_id"] == str(session_id)
        assert call_kwargs["task_id"] == str(task_id)
        assert "timestamp" in call_kwargs

    @patch("agent.events.handlers.logging_handler.logger")
    async def test_uses_error_level_for_failures(
        self, mock_logger, handler: LoggingEventHandler
    ) -> None:
        """Test that error level is used for failure events."""
        event = TaskFailedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            error="Something went wrong",
        )

        await handler.handle(event)

        mock_logger.error.assert_called_once()
        mock_logger.debug.assert_not_called()
        mock_logger.info.assert_not_called()

    @patch("agent.events.handlers.logging_handler.logger")
    async def test_uses_warning_level_for_retries(
        self, mock_logger, handler: LoggingEventHandler
    ) -> None:
        """Test that warning level is used for retry events."""
        event = MilestoneRetryEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            retry_count=2,
            max_retries=3,
        )

        await handler.handle(event)

        mock_logger.warning.assert_called_once()

    @patch("agent.events.handlers.logging_handler.logger")
    async def test_uses_info_level_for_completions(
        self, mock_logger, handler: LoggingEventHandler
    ) -> None:
        """Test that info level is used for completion events."""
        event = TaskCompletedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            final_result="Done",
            total_input_tokens=100,
            total_output_tokens=50,
            total_cost_usd=Decimal("0.01"),
            duration_seconds=10.0,
        )

        await handler.handle(event)

        mock_logger.info.assert_called_once()

    @patch("agent.events.handlers.logging_handler.logger")
    async def test_uses_debug_level_for_other_events(
        self, mock_logger, handler: LoggingEventHandler
    ) -> None:
        """Test that debug level is used for other events."""
        event = LLMChunkEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            chunk="Hello",
            chunk_index=0,
            agent="worker",
        )

        await handler.handle(event)

        mock_logger.debug.assert_called_once()

    @patch("agent.events.handlers.logging_handler.logger")
    async def test_includes_extra_fields_in_log(
        self, mock_logger, handler: LoggingEventHandler
    ) -> None:
        """Test that extra fields are included in log output."""
        milestone_id = uuid4()

        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=milestone_id,
            sequence_number=3,
            agent="conductor",
            status=AgentStatus.STARTED,
            message="Planning",
        )

        await handler.handle(event)

        call_kwargs = mock_logger.debug.call_args[1]

        assert call_kwargs["milestone_id"] == str(milestone_id)
        assert call_kwargs["sequence_number"] == 3
        assert call_kwargs["agent"] == "conductor"
        assert call_kwargs["status"] == "started"
        assert call_kwargs["message"] == "Planning"


class TestLogLevelConfiguration:
    """Tests for log level configuration."""

    def test_default_log_level(self) -> None:
        """Test that default log level is debug."""
        handler = LoggingEventHandler()
        assert handler.log_level == "debug"

    def test_custom_log_level(self) -> None:
        """Test that custom log level is respected."""
        handler = LoggingEventHandler(log_level="info")
        assert handler.log_level == "info"

    @patch("agent.events.handlers.logging_handler.logger")
    async def test_custom_log_level_affects_default_events(self, mock_logger) -> None:
        """Test that custom log level affects default event logging."""
        handler = LoggingEventHandler(log_level="info")

        event = TaskStartedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
        )

        await handler.handle(event)

        # Should use info level (custom default) instead of debug
        mock_logger.info.assert_called_once()
        mock_logger.debug.assert_not_called()


class TestEventSpecificLogging:
    """Tests for event-specific logging behavior."""

    @patch("agent.events.handlers.logging_handler.logger")
    async def test_milestone_status_changed_logging(
        self, mock_logger, handler: LoggingEventHandler
    ) -> None:
        """Test MilestoneStatusChangedEvent logging includes status info."""
        event = MilestoneStatusChangedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=2,
            previous_status=MilestoneStatus.PENDING,
            new_status=MilestoneStatus.IN_PROGRESS,
            agent="worker",
            message="Starting milestone",
        )

        await handler.handle(event)

        call_kwargs = mock_logger.debug.call_args[1]
        assert call_kwargs["sequence_number"] == 2
        assert call_kwargs["agent"] == "worker"
        assert call_kwargs["message"] == "Starting milestone"

    @patch("agent.events.handlers.logging_handler.logger")
    async def test_context_compressed_logging(
        self, mock_logger, handler: LoggingEventHandler
    ) -> None:
        """Test ContextCompressedEvent logging."""
        event = ContextCompressedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            old_message_count=100,
            new_message_count=10,
            tokens_saved_estimate=5000,
        )

        await handler.handle(event)

        mock_logger.debug.assert_called_once()
        call_kwargs = mock_logger.debug.call_args[1]
        assert call_kwargs["event_type"] == "context.compressed"
