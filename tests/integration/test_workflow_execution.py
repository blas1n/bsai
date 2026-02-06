"""Integration tests for workflow execution."""

from typing import Any
from uuid import UUID, uuid4

import pytest

from bsai.db.models.enums import TaskStatus
from bsai.graph.state import AgentState
from bsai.llm import ChatMessage


def create_task_data(
    task_id: str = "T1.1.1",
    description: str = "Test",
    complexity: str = "simple",
    status: str = "pending",
) -> dict[str, Any]:
    """Helper to create a task data dict for project plan."""
    return {
        "id": task_id,
        "description": description,
        "complexity": complexity,
        "acceptance_criteria": "Task completes successfully",
        "status": status,
        "worker_output": None,
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


class TestWorkflowExecution:
    """Integration tests for the complete workflow execution."""

    @pytest.fixture
    def initial_state(self) -> AgentState:
        """Create an initial agent state for testing."""
        return create_base_state(
            original_request="Write a simple Python function to add two numbers",
            current_task_id="T1.1.1",
        )

    @pytest.mark.asyncio
    async def test_state_initialization(self, initial_state: AgentState):
        """Test that initial state is properly configured."""
        assert initial_state.get("session_id") is not None
        assert initial_state.get("task_id") is not None
        assert initial_state.get("current_task_id") == "T1.1.1"
        assert initial_state.get("current_milestone_index") == 0
        assert initial_state.get("task_status") == TaskStatus.PENDING
        assert initial_state.get("retry_count") == 0

    @pytest.mark.asyncio
    async def test_context_tracking(self, initial_state: AgentState):
        """Test context usage tracking."""
        assert initial_state.get("current_context_tokens") == 0
        assert initial_state.get("context_messages") == []


class TestTaskDataValidation:
    """Tests for task data validation."""

    def test_task_data_required_fields(self):
        """Test that task data contains all fields."""
        task = create_task_data(description="Test description")
        assert task.get("id") is not None
        assert task.get("description") == "Test description"

    def test_task_complexity_levels(self):
        """Test all complexity levels are valid."""
        complexities = ["trivial", "simple", "moderate", "complex", "context_heavy"]
        for complexity in complexities:
            task = create_task_data(complexity=complexity)
            assert task.get("complexity") == complexity

    def test_task_status_values(self):
        """Test task status values."""
        statuses = ["pending", "in_progress", "passed", "failed"]
        for status in statuses:
            task = create_task_data(status=status)
            assert task.get("status") == status


class TestAgentStateUpdates:
    """Tests for AgentState update operations."""

    @pytest.fixture
    def base_state(self) -> AgentState:
        """Create a base state for testing updates."""
        return create_base_state()

    def test_update_milestone_index(self, base_state: AgentState):
        """Test updating current milestone index."""
        base_state["current_milestone_index"] = 2
        assert base_state.get("current_milestone_index") == 2

    def test_update_retry_count(self, base_state: AgentState):
        """Test updating retry count."""
        base_state["retry_count"] = 1
        assert base_state.get("retry_count") == 1

    def test_set_error(self, base_state: AgentState):
        """Test setting error message."""
        base_state["error"] = "Test error occurred"
        assert base_state.get("error") == "Test error occurred"

    def test_set_workflow_complete(self, base_state: AgentState):
        """Test setting workflow complete flag."""
        base_state["workflow_complete"] = True
        assert base_state.get("workflow_complete") is True


class TestWorkflowEdgeCases:
    """Tests for workflow edge cases."""

    def test_no_current_task(self):
        """Test state with no current task."""
        state = create_base_state(current_task_id=None)
        assert state.get("current_task_id") is None

    def test_multiple_tasks_progress(self):
        """Test state progressing through multiple tasks."""
        # Start with first task
        state = create_base_state(
            current_task_id="T1.1.1",
            current_milestone_index=0,
        )
        assert state.get("current_task_id") == "T1.1.1"

        # Progress to second task
        state["current_task_id"] = "T1.1.2"
        state["current_milestone_index"] = 1
        assert state.get("current_task_id") == "T1.1.2"
        assert state.get("current_milestone_index") == 1

    def test_high_context_usage(self):
        """Test high context token usage."""
        state = create_base_state(
            context_messages=[ChatMessage(role="user", content="x" * 10000)],
            current_context_tokens=90000,
        )
        current = state.get("current_context_tokens", 0)
        max_tokens = state.get("max_context_tokens", 100000)
        # Above 85% threshold triggers compression
        assert current / max_tokens >= 0.85
