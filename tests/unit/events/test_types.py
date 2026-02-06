"""Tests for Event type definitions."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from bsai.api.schemas.websocket import PreviousMilestoneInfo
from bsai.events.types import (
    AgentActivityEvent,
    AgentStatus,
    BreakpointHitEvent,
    BreakpointResumedEvent,
    ContextCompressedEvent,
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


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values(self) -> None:
        """Test that EventType has expected values."""
        # Task lifecycle
        assert EventType.TASK_CREATED == "task.created"
        assert EventType.TASK_STARTED == "task.started"
        assert EventType.TASK_PROGRESS == "task.progress"
        assert EventType.TASK_COMPLETED == "task.completed"
        assert EventType.TASK_FAILED == "task.failed"
        assert EventType.TASK_CANCELLED == "task.cancelled"

        # Milestone lifecycle
        assert EventType.MILESTONE_CREATED == "milestone.created"
        assert EventType.MILESTONE_STARTED == "milestone.started"
        assert EventType.MILESTONE_STATUS_CHANGED == "milestone.status_changed"
        assert EventType.MILESTONE_COMPLETED == "milestone.completed"
        assert EventType.MILESTONE_FAILED == "milestone.failed"
        assert EventType.MILESTONE_RETRY == "milestone.retry"

        # Agent activity
        assert EventType.AGENT_STARTED == "bsai.started"
        assert EventType.AGENT_COMPLETED == "bsai.completed"
        assert EventType.AGENT_FAILED == "bsai.failed"

        # LLM streaming
        assert EventType.LLM_CHUNK == "llm.chunk"
        assert EventType.LLM_COMPLETE == "llm.complete"

        # Context management
        assert EventType.CONTEXT_COMPRESSED == "context.compressed"

        # Breakpoint
        assert EventType.BREAKPOINT_HIT == "breakpoint.hit"
        assert EventType.BREAKPOINT_RESUMED == "breakpoint.resumed"
        assert EventType.BREAKPOINT_REJECTED == "breakpoint.rejected"

    def test_event_type_is_string(self) -> None:
        """Test that EventType values are strings."""
        assert isinstance(EventType.TASK_STARTED.value, str)
        assert str(EventType.TASK_STARTED) == "task.started"


class TestAgentStatus:
    """Tests for AgentStatus enum."""

    def test_agent_status_values(self) -> None:
        """Test that AgentStatus has expected values."""
        assert AgentStatus.STARTED == "started"
        assert AgentStatus.COMPLETED == "completed"
        assert AgentStatus.FAILED == "failed"

    def test_agent_status_is_string(self) -> None:
        """Test that AgentStatus values are strings."""
        assert isinstance(AgentStatus.STARTED.value, str)
        assert str(AgentStatus.STARTED) == "started"


class TestMilestoneStatus:
    """Tests for MilestoneStatus re-export."""

    def test_milestone_status_values(self) -> None:
        """Test that MilestoneStatus has expected values."""
        assert MilestoneStatus.PENDING == "pending"
        assert MilestoneStatus.IN_PROGRESS == "in_progress"
        assert MilestoneStatus.PASSED == "passed"
        assert MilestoneStatus.FAILED == "failed"

    def test_milestone_status_no_completed(self) -> None:
        """Test that MilestoneStatus doesn't have 'completed' value."""
        # Backend uses 'passed', not 'completed'
        values = [status.value for status in MilestoneStatus]
        assert "completed" not in values
        assert "passed" in values


class TestBaseEvent:
    """Tests for base Event class."""

    def test_event_timestamp_auto_generated(self) -> None:
        """Test that timestamp is auto-generated."""
        before = datetime.now(UTC)
        event = TaskStartedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
        )
        after = datetime.now(UTC)

        assert before <= event.timestamp <= after

    def test_event_serialization(self) -> None:
        """Test that events can be serialized to dict."""
        session_id = uuid4()
        task_id = uuid4()

        event = TaskStartedEvent(
            session_id=session_id,
            task_id=task_id,
            original_request="Test request",
            milestone_count=3,
        )

        data = event.model_dump()

        assert data["type"] == "task.started"
        assert data["session_id"] == session_id
        assert data["task_id"] == task_id
        assert data["original_request"] == "Test request"
        assert data["milestone_count"] == 3


class TestTaskEvents:
    """Tests for Task-related events."""

    def test_task_started_event(self) -> None:
        """Test TaskStartedEvent creation."""
        event = TaskStartedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Build a feature",
            milestone_count=5,
            previous_milestones=[
                PreviousMilestoneInfo(
                    id=uuid4(),
                    sequence_number=1,
                    description="First milestone",
                    complexity="low",
                    status="passed",
                )
            ],
            trace_url="https://example.com/trace/123",
        )

        assert event.type == EventType.TASK_STARTED
        assert event.original_request == "Build a feature"
        assert event.milestone_count == 5
        assert len(event.previous_milestones) == 1
        assert event.trace_url == "https://example.com/trace/123"

    def test_task_started_event_defaults(self) -> None:
        """Test TaskStartedEvent with defaults."""
        event = TaskStartedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
        )

        assert event.milestone_count == 0
        assert event.previous_milestones == []
        assert event.trace_url == ""

    def test_task_progress_event(self) -> None:
        """Test TaskProgressEvent creation."""
        event = TaskProgressEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            current_milestone=2,
            total_milestones=5,
            progress=0.4,
            current_milestone_title="Implement feature",
        )

        assert event.type == EventType.TASK_PROGRESS
        assert event.current_milestone == 2
        assert event.total_milestones == 5
        assert event.progress == 0.4
        assert event.current_milestone_title == "Implement feature"

    def test_task_completed_event(self) -> None:
        """Test TaskCompletedEvent creation."""
        event = TaskCompletedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            final_result="Task completed successfully",
            total_input_tokens=5000,
            total_output_tokens=2000,
            total_cost_usd=Decimal("0.15"),
            duration_seconds=120.5,
            trace_url="https://example.com/trace/123",
        )

        assert event.type == EventType.TASK_COMPLETED
        assert event.final_result == "Task completed successfully"
        assert event.total_input_tokens == 5000
        assert event.total_output_tokens == 2000
        assert event.total_cost_usd == Decimal("0.15")
        assert event.duration_seconds == 120.5
        assert event.trace_url == "https://example.com/trace/123"

    def test_task_failed_event(self) -> None:
        """Test TaskFailedEvent creation."""
        event = TaskFailedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            error="Something went wrong",
            failed_milestone=3,
        )

        assert event.type == EventType.TASK_FAILED
        assert event.error == "Something went wrong"
        assert event.failed_milestone == 3

    def test_task_failed_event_no_milestone(self) -> None:
        """Test TaskFailedEvent without failed milestone."""
        event = TaskFailedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            error="Early failure",
        )

        assert event.failed_milestone is None


class TestMilestoneEvents:
    """Tests for Milestone-related events."""

    def test_milestone_status_changed_event(self) -> None:
        """Test MilestoneStatusChangedEvent creation."""
        event = MilestoneStatusChangedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=2,
            previous_status=MilestoneStatus.PENDING,
            new_status=MilestoneStatus.IN_PROGRESS,
            agent="worker",
            message="Starting milestone",
            details={"key": "value"},
        )

        assert event.type == EventType.MILESTONE_STATUS_CHANGED
        assert event.sequence_number == 2
        assert event.previous_status == MilestoneStatus.PENDING
        assert event.new_status == MilestoneStatus.IN_PROGRESS
        assert event.agent == "worker"
        assert event.message == "Starting milestone"
        assert event.details == {"key": "value"}

    def test_milestone_status_changed_no_details(self) -> None:
        """Test MilestoneStatusChangedEvent without details."""
        event = MilestoneStatusChangedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            previous_status=MilestoneStatus.IN_PROGRESS,
            new_status=MilestoneStatus.PASSED,
            agent="qa",
            message="Milestone passed",
        )

        assert event.details is None

    def test_milestone_retry_event(self) -> None:
        """Test MilestoneRetryEvent creation."""
        event = MilestoneRetryEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=3,
            retry_count=2,
            max_retries=3,
            feedback="Need to fix formatting",
        )

        assert event.type == EventType.MILESTONE_RETRY
        assert event.sequence_number == 3
        assert event.retry_count == 2
        assert event.max_retries == 3
        assert event.feedback == "Need to fix formatting"

    def test_milestone_retry_event_defaults(self) -> None:
        """Test MilestoneRetryEvent with defaults."""
        event = MilestoneRetryEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            retry_count=1,
        )

        assert event.max_retries == 3
        assert event.feedback is None


class TestAgentActivityEvent:
    """Tests for AgentActivityEvent."""

    def test_agent_started(self) -> None:
        """Test AgentActivityEvent for started status."""
        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="conductor",
            status=AgentStatus.STARTED,
            message="Planning milestones",
        )

        assert event.type == EventType.AGENT_STARTED
        assert event.agent == "conductor"
        assert event.status == AgentStatus.STARTED
        assert event.message == "Planning milestones"

    def test_agent_completed(self) -> None:
        """Test AgentActivityEvent for completed status."""
        event = AgentActivityEvent(
            type=EventType.AGENT_COMPLETED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.COMPLETED,
            message="Task executed",
            details={
                "output": "Result",
                "tokens_used": 100,
            },
        )

        assert event.type == EventType.AGENT_COMPLETED
        assert event.status == AgentStatus.COMPLETED
        assert event.details is not None
        assert event.details["output"] == "Result"

    def test_agent_failed(self) -> None:
        """Test AgentActivityEvent for failed status."""
        event = AgentActivityEvent(
            type=EventType.AGENT_FAILED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="qa",
            status=AgentStatus.FAILED,
            message="QA check failed",
        )

        assert event.type == EventType.AGENT_FAILED
        assert event.status == AgentStatus.FAILED


class TestLLMStreamingEvents:
    """Tests for LLM streaming events."""

    def test_llm_chunk_event(self) -> None:
        """Test LLMChunkEvent creation."""
        event = LLMChunkEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            chunk="Hello ",
            chunk_index=0,
            agent="worker",
        )

        assert event.type == EventType.LLM_CHUNK
        assert event.chunk == "Hello "
        assert event.chunk_index == 0
        assert event.agent == "worker"

    def test_llm_complete_event(self) -> None:
        """Test LLMCompleteEvent creation."""
        event = LLMCompleteEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            full_content="Hello world!",
            tokens_used=5,
            agent="worker",
        )

        assert event.type == EventType.LLM_COMPLETE
        assert event.full_content == "Hello world!"
        assert event.tokens_used == 5
        assert event.agent == "worker"


class TestContextCompressedEvent:
    """Tests for ContextCompressedEvent."""

    def test_context_compressed_event(self) -> None:
        """Test ContextCompressedEvent creation."""
        event = ContextCompressedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            old_message_count=100,
            new_message_count=10,
            tokens_saved_estimate=5000,
        )

        assert event.type == EventType.CONTEXT_COMPRESSED
        assert event.old_message_count == 100
        assert event.new_message_count == 10
        assert event.tokens_saved_estimate == 5000


class TestBreakpointEvents:
    """Tests for Breakpoint events."""

    def test_breakpoint_hit_event(self) -> None:
        """Test BreakpointHitEvent creation."""
        event = BreakpointHitEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            node_name="execute_worker",
            agent_type="worker",
            current_milestone_index=2,
            total_milestones=5,
            milestones=[
                {"description": "Setup", "status": "passed"},
                {"description": "Implement", "status": "in_progress"},
            ],
            last_worker_output="Previous output",
            last_qa_result={"decision": "passed", "feedback": None},
        )

        assert event.type == EventType.BREAKPOINT_HIT
        assert event.node_name == "execute_worker"
        assert event.agent_type == "worker"
        assert event.current_milestone_index == 2
        assert event.total_milestones == 5
        assert len(event.milestones) == 2
        assert event.last_worker_output == "Previous output"
        assert event.last_qa_result is not None

    def test_breakpoint_hit_event_minimal(self) -> None:
        """Test BreakpointHitEvent with minimal data."""
        event = BreakpointHitEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            node_name="verify_qa",
            agent_type="qa",
            current_milestone_index=1,
            total_milestones=3,
            milestones=[],
        )

        assert event.last_worker_output is None
        assert event.last_qa_result is None

    def test_breakpoint_resumed_event(self) -> None:
        """Test BreakpointResumedEvent creation."""
        event = BreakpointResumedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            node_name="execute_worker",
            user_input="Continue with modified approach",
        )

        assert event.type == EventType.BREAKPOINT_RESUMED
        assert event.node_name == "execute_worker"
        assert event.user_input == "Continue with modified approach"

    def test_breakpoint_resumed_event_no_input(self) -> None:
        """Test BreakpointResumedEvent without user input."""
        event = BreakpointResumedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            node_name="verify_qa",
        )

        assert event.user_input is None


class TestEventModelConfig:
    """Tests for Event model configuration."""

    def test_use_enum_values(self) -> None:
        """Test that enum values are used in serialization."""
        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.STARTED,
            message="Starting",
        )

        data = event.model_dump()

        # Should be string values, not enum objects
        assert data["type"] == "bsai.started"
        assert data["status"] == "started"
        assert isinstance(data["type"], str)
        assert isinstance(data["status"], str)

    def test_json_serialization(self) -> None:
        """Test that events can be serialized to JSON."""
        import json

        event = TaskStartedEvent(
            session_id=uuid4(),
            task_id=uuid4(),
            original_request="Test",
        )

        json_str = event.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["type"] == "task.started"
        assert parsed["original_request"] == "Test"
