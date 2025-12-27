"""Tests for workflow state definitions."""

from uuid import uuid4

from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.graph.state import AgentState, MilestoneData


class TestMilestoneData:
    """Tests for MilestoneData TypedDict."""

    def test_create_milestone_data(self) -> None:
        """Test creating a MilestoneData instance."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Setup project",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Project initialized",
            status=MilestoneStatus.PENDING,
            selected_model=None,
            generated_prompt=None,
            worker_output=None,
            qa_feedback=None,
            retry_count=0,
        )

        assert milestone["description"] == "Setup project"
        assert milestone["complexity"] == TaskComplexity.SIMPLE
        assert milestone["status"] == MilestoneStatus.PENDING
        assert milestone["retry_count"] == 0

    def test_milestone_data_with_all_fields(self) -> None:
        """Test MilestoneData with all fields populated."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Build feature",
            complexity=TaskComplexity.COMPLEX,
            acceptance_criteria="Feature works",
            status=MilestoneStatus.PASSED,
            selected_model="gpt-4o",
            generated_prompt="Optimized prompt text",
            worker_output="Feature implementation",
            qa_feedback="Looks good",
            retry_count=1,
        )

        assert milestone["selected_model"] == "gpt-4o"
        assert milestone["generated_prompt"] == "Optimized prompt text"
        assert milestone["worker_output"] == "Feature implementation"
        assert milestone["qa_feedback"] == "Looks good"


class TestAgentState:
    """Tests for AgentState TypedDict."""

    def test_create_minimal_state(self) -> None:
        """Test creating AgentState with minimal fields."""
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "original_request": "Build a web scraper",
        }

        assert "session_id" in state
        assert state["original_request"] == "Build a web scraper"

    def test_create_full_state(self) -> None:
        """Test creating AgentState with all fields."""
        session_id = uuid4()
        task_id = uuid4()

        milestone = MilestoneData(
            id=uuid4(),
            description="Setup",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.PENDING,
            selected_model=None,
            generated_prompt=None,
            worker_output=None,
            qa_feedback=None,
            retry_count=0,
        )

        state: AgentState = {
            "session_id": session_id,
            "task_id": task_id,
            "original_request": "Build something",
            "task_status": TaskStatus.IN_PROGRESS,
            "milestones": [milestone],
            "current_milestone_index": 0,
            "current_prompt": None,
            "current_output": None,
            "current_qa_decision": None,
            "current_qa_feedback": None,
            "retry_count": 0,
            "context_messages": [],
            "context_summary": None,
            "current_context_tokens": 0,
            "max_context_tokens": 100000,
            "needs_compression": False,
            "error": None,
            "error_node": None,
            "should_continue": True,
            "workflow_complete": False,
        }

        assert state["session_id"] == session_id
        assert state["task_status"] == TaskStatus.IN_PROGRESS
        assert len(state["milestones"]) == 1
        assert state["max_context_tokens"] == 100000
        assert state["workflow_complete"] is False

    def test_partial_state_update(self) -> None:
        """Test that partial state updates work correctly."""
        # Initial state
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "original_request": "Test",
            "retry_count": 0,
        }

        # Simulate partial update (as returned by node functions)
        update: AgentState = {
            "retry_count": 1,
            "current_qa_decision": "retry",
        }

        # Merge (simulating LangGraph behavior)
        merged = {**state, **update}

        assert merged["retry_count"] == 1
        assert merged["current_qa_decision"] == "retry"
        assert merged["original_request"] == "Test"

    def test_immutable_pattern(self) -> None:
        """Test that state updates create new dicts (immutable pattern)."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Test",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.PENDING,
            selected_model=None,
            generated_prompt=None,
            worker_output=None,
            qa_feedback=None,
            retry_count=0,
        )

        state: AgentState = {
            "milestones": [milestone],
            "current_milestone_index": 0,
        }

        # Create updated milestone (immutable pattern)
        updated_milestone = dict(milestone)
        updated_milestone["status"] = MilestoneStatus.IN_PROGRESS

        updated_milestones = list(state["milestones"])
        updated_milestones[0] = MilestoneData(**updated_milestone)  # type: ignore[misc]

        new_state: AgentState = {
            **state,
            "milestones": updated_milestones,
        }

        # Original state should be unchanged
        assert state["milestones"][0]["status"] == MilestoneStatus.PENDING
        # New state should have the update
        assert new_state["milestones"][0]["status"] == MilestoneStatus.IN_PROGRESS
