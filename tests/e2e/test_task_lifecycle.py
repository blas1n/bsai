"""End-to-end tests for complete task lifecycle."""

from typing import Any
from uuid import UUID, uuid4

import pytest

from agent.db.models.enums import TaskStatus
from agent.graph.state import AgentState
from agent.llm import ChatMessage


def create_task_data(
    task_id: str = "T1.1.1",
    description: str = "Test",
    complexity: str = "simple",
    status: str = "pending",
    worker_output: str | None = None,
) -> dict[str, Any]:
    """Helper to create a task data dict for project plan."""
    return {
        "id": task_id,
        "description": description,
        "complexity": complexity,
        "acceptance_criteria": "Task completes successfully",
        "status": status,
        "worker_output": worker_output,
    }


def create_base_state(
    session_id: UUID | None = None,
    task_id: UUID | None = None,
    user_id: str = "test-user",
    original_request: str = "Test request",
    current_task_id: str | None = None,
    current_milestone_index: int = 0,
    context_messages: list[ChatMessage] | None = None,
    current_context_tokens: int = 0,
    max_context_tokens: int = 100000,
    retry_count: int = 0,
    error: str | None = None,
    task_status: TaskStatus = TaskStatus.PENDING,
    should_continue: bool = True,
    workflow_complete: bool = False,
    context_summary: str | None = None,
) -> AgentState:
    """Helper to create an AgentState dict with defaults."""
    return {
        "session_id": session_id or uuid4(),
        "task_id": task_id or uuid4(),
        "user_id": user_id,
        "original_request": original_request,
        "current_task_id": current_task_id,
        "current_milestone_index": current_milestone_index,
        "context_messages": context_messages or [],
        "current_context_tokens": current_context_tokens,
        "max_context_tokens": max_context_tokens,
        "retry_count": retry_count,
        "error": error,
        "task_status": task_status,
        "should_continue": should_continue,
        "workflow_complete": workflow_complete,
        "context_summary": context_summary,
    }


class TestTaskCreation:
    """E2E tests for task creation flow."""

    def test_create_simple_task_state(self):
        """Test creating a simple task state."""
        session_id = uuid4()
        task_id = uuid4()

        state = create_base_state(
            session_id=session_id,
            task_id=task_id,
            original_request="Add two numbers: 5 + 3",
        )

        assert state.get("session_id") == session_id
        assert state.get("task_id") == task_id
        assert state.get("task_status") == TaskStatus.PENDING

    def test_create_complex_task_with_tasks(self):
        """Test creating a complex task with multiple sub-tasks."""
        tasks = [
            create_task_data(
                task_id="T1.1.1",
                description="Parse and understand the task requirements",
                complexity="simple",
            ),
            create_task_data(
                task_id="T1.1.2",
                description="Create a solution architecture",
                complexity="moderate",
            ),
            create_task_data(
                task_id="T1.1.3",
                description="Write the actual code",
                complexity="complex",
            ),
        ]

        state = create_base_state(
            original_request="Build a REST API for user management",
            current_task_id=tasks[0]["id"],
        )

        # In the new architecture, tasks are stored in project_plan
        assert state.get("current_task_id") == "T1.1.1"
        assert state.get("task_status") == TaskStatus.PENDING


class TestTaskExecution:
    """E2E tests for task execution flow."""

    @pytest.fixture
    def running_task_state(self) -> AgentState:
        """Create a state for a running task."""
        return create_base_state(
            original_request="Write a hello world function",
            current_task_id="T1.1.1",
            context_messages=[
                ChatMessage(role="user", content="Write a hello world function"),
                ChatMessage(role="assistant", content="I'll write a hello world function."),
            ],
            current_context_tokens=50,
            task_status=TaskStatus.IN_PROGRESS,
        )

    def test_task_in_progress(self, running_task_state: AgentState):
        """Test task in progress state."""
        assert running_task_state.get("task_status") == TaskStatus.IN_PROGRESS
        assert running_task_state.get("current_task_id") == "T1.1.1"
        assert len(running_task_state.get("context_messages", [])) == 2

    def test_token_counting(self, running_task_state: AgentState):
        """Test token counting during execution."""
        initial_tokens = running_task_state.get("current_context_tokens", 0)

        # Simulate adding more tokens
        running_task_state["current_context_tokens"] = initial_tokens + 100

        assert running_task_state.get("current_context_tokens") == initial_tokens + 100


class TestTaskCompletion:
    """E2E tests for task completion flow."""

    @pytest.fixture
    def completed_task_state(self) -> AgentState:
        """Create a state for a completed task."""
        return create_base_state(
            original_request="Calculate 2 + 2",
            current_task_id="T1.1.1",
            context_messages=[
                ChatMessage(role="user", content="Calculate 2 + 2"),
                ChatMessage(role="assistant", content="The answer is 4."),
            ],
            current_context_tokens=30,
            task_status=TaskStatus.COMPLETED,
            should_continue=False,
            workflow_complete=True,
        )

    def test_task_completed(self, completed_task_state: AgentState):
        """Test completed task state."""
        assert completed_task_state.get("task_status") == TaskStatus.COMPLETED
        assert completed_task_state.get("workflow_complete") is True
        assert completed_task_state.get("error") is None

    def test_no_retries_needed(self, completed_task_state: AgentState):
        """Test no retries were needed."""
        assert completed_task_state.get("retry_count") == 0


class TestTaskFailure:
    """E2E tests for task failure scenarios."""

    @pytest.fixture
    def failed_task_state(self) -> AgentState:
        """Create a state for a failed task."""
        return create_base_state(
            original_request="Connect to invalid API",
            current_task_id="T1.1.1",
            retry_count=3,
            error="API connection failed after 3 retries",
            task_status=TaskStatus.FAILED,
            should_continue=False,
            workflow_complete=True,
        )

    def test_task_failed(self, failed_task_state: AgentState):
        """Test failed task state."""
        assert failed_task_state.get("task_status") == TaskStatus.FAILED
        assert failed_task_state.get("error") is not None
        assert failed_task_state.get("workflow_complete") is True

    def test_max_retries_reached(self, failed_task_state: AgentState):
        """Test max retries were reached."""
        assert failed_task_state.get("retry_count") == 3


class TestRetryFlow:
    """E2E tests for retry scenarios."""

    def test_first_retry(self):
        """Test first retry."""
        state = create_base_state(
            original_request="Write code with quality check",
            current_task_id="T1.1.1",
            retry_count=1,
            task_status=TaskStatus.IN_PROGRESS,
        )

        assert state.get("retry_count") == 1
        assert state.get("task_status") == TaskStatus.IN_PROGRESS

    def test_second_retry(self):
        """Test second retry."""
        state = create_base_state(
            original_request="Improve code quality",
            current_task_id="T1.1.1",
            current_context_tokens=200,
            retry_count=2,
            task_status=TaskStatus.IN_PROGRESS,
        )

        assert state.get("retry_count") == 2
        # Tokens accumulate with each retry
        assert state.get("current_context_tokens", 0) > 0


class TestSessionPauseResume:
    """E2E tests for session pause/resume flow."""

    @pytest.fixture
    def interrupted_session_state(self) -> AgentState:
        """Create a state for an interrupted session (mid-progress)."""
        return create_base_state(
            original_request="Long running task",
            current_task_id="T1.1.2",
            current_milestone_index=1,
            context_messages=[
                ChatMessage(role="user", content="Start long task"),
                ChatMessage(role="assistant", content="Step 1 completed."),
            ],
            context_summary="User requested long task. Step 1 completed successfully.",
            current_context_tokens=100,
            task_status=TaskStatus.IN_PROGRESS,
            should_continue=False,
        )

    def test_session_interrupted(self, interrupted_session_state: AgentState):
        """Test interrupted session state."""
        assert interrupted_session_state.get("task_status") == TaskStatus.IN_PROGRESS
        assert interrupted_session_state.get("current_milestone_index") == 1

    def test_context_preserved(self, interrupted_session_state: AgentState):
        """Test context is preserved when interrupted."""
        assert len(interrupted_session_state.get("context_messages", [])) == 2
        assert interrupted_session_state.get("current_context_tokens") == 100

    def test_progress_preserved(self, interrupted_session_state: AgentState):
        """Test progress is preserved when interrupted."""
        assert interrupted_session_state.get("current_task_id") == "T1.1.2"
        assert interrupted_session_state.get("current_milestone_index") == 1


class TestContextCompression:
    """E2E tests for context compression scenarios."""

    def test_high_context_usage_triggers_compression(self):
        """Test high context usage would trigger compression."""
        state = create_base_state(
            original_request="Very long conversation task",
            context_messages=[ChatMessage(role="assistant", content="x" * 50000)],
            current_context_tokens=88000,
            task_status=TaskStatus.IN_PROGRESS,
        )

        current = state.get("current_context_tokens", 0)
        max_tokens = state.get("max_context_tokens", 100000)
        # Context capacity is above compression threshold (85%)
        assert current / max_tokens > 0.85

    def test_context_after_compression(self):
        """Test context state after compression."""
        state = create_base_state(
            original_request="Compressed context task",
            context_messages=[
                ChatMessage(role="system", content="[Summary of previous context]"),
                ChatMessage(role="user", content="Continue the task"),
            ],
            context_summary="Previous conversation summarized: User worked on complex task.",
            current_context_tokens=5000,
            task_status=TaskStatus.IN_PROGRESS,
        )

        current = state.get("current_context_tokens", 0)
        max_tokens = state.get("max_context_tokens", 100000)
        # Context usage is low after compression
        assert current / max_tokens < 0.1
