"""Tests for workflow state definitions."""

from uuid import uuid4

from agent.db.models.enums import TaskStatus
from agent.graph.state import AgentState


class TestAgentState:
    """Tests for AgentState TypedDict."""

    def test_create_minimal_state(self) -> None:
        """Test creating AgentState with minimal required fields."""
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test-user",
            "original_request": "Build a web scraper",
        }

        assert "session_id" in state
        assert state["original_request"] == "Build a web scraper"

    def test_create_full_state(self) -> None:
        """Test creating AgentState with all fields."""
        session_id = uuid4()
        task_id = uuid4()

        state: AgentState = {
            "session_id": session_id,
            "task_id": task_id,
            "user_id": "test-user",
            "original_request": "Build something",
            "task_status": TaskStatus.IN_PROGRESS,
            "project_plan": None,
            "plan_status": None,
            "current_task_id": "T1",
            "current_output": None,
            "current_qa_decision": None,
            "current_qa_feedback": None,
            "retry_count": 0,
            "context_messages": [],
            "context_summary": None,
            "current_context_tokens": 0,
            "max_context_tokens": 100000,
            "error": None,
            "error_node": None,
            "should_continue": True,
            "workflow_complete": False,
        }

        assert state["session_id"] == session_id
        assert state["task_status"] == TaskStatus.IN_PROGRESS
        assert state["max_context_tokens"] == 100000
        assert state["workflow_complete"] is False

    def test_partial_state_update(self) -> None:
        """Test that partial state updates work correctly."""
        # Initial state
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test-user",
            "original_request": "Test",
            "retry_count": 0,
        }

        # Simulate partial update (as returned by node functions)
        update: dict[str, int | str] = {
            "retry_count": 1,
            "current_qa_decision": "retry",
        }

        # Merge (simulating LangGraph behavior)
        merged = {**state, **update}

        assert merged["retry_count"] == 1
        assert merged["current_qa_decision"] == "retry"
        assert merged["original_request"] == "Test"

    def test_state_with_project_plan(self) -> None:
        """Test state with project plan fields."""
        from unittest.mock import MagicMock

        mock_plan = MagicMock()
        mock_plan.id = uuid4()
        mock_plan.plan_data = {"tasks": [{"id": "T1", "description": "Task 1"}]}

        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test-user",
            "original_request": "Build something",
            "project_plan": mock_plan,
            "current_task_id": "T1",
        }

        assert state["project_plan"] is mock_plan
        assert state["current_task_id"] == "T1"

    def test_state_with_dependency_graph(self) -> None:
        """Test state with dependency graph fields."""
        from unittest.mock import MagicMock

        mock_graph = MagicMock()

        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test-user",
            "original_request": "Build something",
            "dependency_graph": mock_graph,
            "ready_tasks": ["T1", "T2"],
        }

        assert state["dependency_graph"] is mock_graph
        assert state["ready_tasks"] == ["T1", "T2"]

    def test_state_with_plan_review_fields(self) -> None:
        """Test state with plan review (human-in-the-loop) fields."""
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test-user",
            "original_request": "Build something",
            "waiting_for_plan_review": True,
            "revision_requested": False,
            "revision_feedback": None,
        }

        assert state["waiting_for_plan_review"] is True
        assert state["revision_requested"] is False

    def test_state_with_breakpoint_fields(self) -> None:
        """Test state with breakpoint configuration fields."""
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test-user",
            "original_request": "Build something",
            "breakpoint_enabled": True,
            "breakpoint_nodes": ["verify_qa", "execute_worker"],
            "breakpoint_user_input": None,
        }

        assert state["breakpoint_enabled"] is True
        assert "verify_qa" in state["breakpoint_nodes"]

    def test_state_with_cost_tracking(self) -> None:
        """Test state with token and cost tracking fields."""
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test-user",
            "original_request": "Build something",
            "total_input_tokens": 1000,
            "total_output_tokens": 500,
            "total_cost_usd": "0.0150",
        }

        assert state["total_input_tokens"] == 1000
        assert state["total_output_tokens"] == 500
        assert state["total_cost_usd"] == "0.0150"
