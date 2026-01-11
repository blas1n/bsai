"""Integration tests for workflow execution."""

from uuid import UUID, uuid4

import pytest

from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.graph.state import AgentState, MilestoneData
from agent.llm import ChatMessage


def create_milestone(
    description: str = "Test",
    complexity: TaskComplexity = TaskComplexity.SIMPLE,
    status: MilestoneStatus = MilestoneStatus.PENDING,
) -> MilestoneData:
    """Helper to create a MilestoneData dict."""
    return {
        "id": uuid4(),
        "description": description,
        "complexity": complexity,
        "acceptance_criteria": "",
        "status": status,
        "selected_model": None,
        "generated_prompt": None,
        "worker_output": None,
        "qa_feedback": None,
        "retry_count": 0,
    }


def create_base_state(
    session_id: UUID | None = None,
    task_id: UUID | None = None,
    user_id: str = "test-user",
    original_request: str = "Test request",
    milestones: list[MilestoneData] | None = None,
    current_milestone_index: int = 0,
    context_messages: list[ChatMessage] | None = None,
    current_context_tokens: int = 0,
    max_context_tokens: int = 100000,
    retry_count: int = 0,
    error: str | None = None,
    task_status: TaskStatus = TaskStatus.PENDING,
    should_continue: bool = True,
    workflow_complete: bool = False,
    needs_compression: bool = False,
    context_summary: str | None = None,
) -> AgentState:
    """Helper to create an AgentState dict with defaults."""
    return {
        "session_id": session_id or uuid4(),
        "task_id": task_id or uuid4(),
        "user_id": user_id,
        "original_request": original_request,
        "milestones": milestones or [],
        "current_milestone_index": current_milestone_index,
        "context_messages": context_messages or [],
        "current_context_tokens": current_context_tokens,
        "max_context_tokens": max_context_tokens,
        "retry_count": retry_count,
        "error": error,
        "task_status": task_status,
        "should_continue": should_continue,
        "workflow_complete": workflow_complete,
        "needs_compression": needs_compression,
        "context_summary": context_summary,
    }


class TestWorkflowExecution:
    """Integration tests for the complete workflow execution."""

    @pytest.fixture
    def initial_state(self) -> AgentState:
        """Create an initial agent state for testing."""
        return create_base_state(
            original_request="Write a simple Python function to add two numbers",
            milestones=[
                create_milestone(
                    description="Create a function that adds two numbers",
                    complexity=TaskComplexity.SIMPLE,
                )
            ],
        )

    @pytest.mark.asyncio
    async def test_state_initialization(self, initial_state: AgentState):
        """Test that initial state is properly configured."""
        assert initial_state.get("session_id") is not None
        assert initial_state.get("task_id") is not None
        assert len(initial_state.get("milestones", [])) == 1
        assert initial_state.get("current_milestone_index") == 0
        assert initial_state.get("task_status") == TaskStatus.PENDING
        assert initial_state.get("retry_count") == 0

    @pytest.mark.asyncio
    async def test_milestone_data_structure(self, initial_state: AgentState):
        """Test milestone data structure."""
        milestones = initial_state.get("milestones", [])
        assert len(milestones) == 1
        milestone = milestones[0]
        assert milestone.get("complexity") == TaskComplexity.SIMPLE
        assert milestone.get("status") == MilestoneStatus.PENDING
        assert milestone.get("acceptance_criteria") is not None

    @pytest.mark.asyncio
    async def test_context_tracking(self, initial_state: AgentState):
        """Test context usage tracking."""
        assert initial_state.get("current_context_tokens") == 0
        assert initial_state.get("context_messages") == []


class TestMilestoneDataValidation:
    """Tests for MilestoneData validation."""

    def test_milestone_data_required_fields(self):
        """Test that MilestoneData contains all fields."""
        milestone = create_milestone(description="Test description")
        assert milestone.get("id") is not None
        assert milestone.get("description") == "Test description"

    def test_milestone_complexity_levels(self):
        """Test all complexity levels are valid."""
        for complexity in list(TaskComplexity):
            milestone = create_milestone(complexity=complexity)
            assert milestone.get("complexity") == complexity

    def test_milestone_status_transitions(self):
        """Test milestone status values."""
        statuses = [
            MilestoneStatus.PENDING,
            MilestoneStatus.IN_PROGRESS,
            MilestoneStatus.PASSED,
            MilestoneStatus.FAILED,
        ]
        for status in statuses:
            milestone = create_milestone(status=status)
            assert milestone.get("status") == status


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

    def test_empty_milestones(self):
        """Test state with no milestones."""
        state = create_base_state(milestones=[])
        assert len(state.get("milestones", [])) == 0

    def test_multiple_milestones(self):
        """Test state with multiple milestones."""
        milestones = [create_milestone(description=f"Description {i}") for i in range(1, 6)]
        state = create_base_state(milestones=milestones)
        assert len(state.get("milestones", [])) == 5

    def test_high_context_usage(self):
        """Test high context token usage."""
        state = create_base_state(
            context_messages=[ChatMessage(role="user", content="x" * 10000)],
            current_context_tokens=90000,
            needs_compression=True,
        )
        current = state.get("current_context_tokens", 0)
        max_tokens = state.get("max_context_tokens", 100000)
        # Above 85% threshold triggers compression
        assert current / max_tokens >= 0.85
