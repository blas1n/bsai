"""Tests for task summary node."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.nodes.task_summary import task_summary_node
from agent.graph.state import AgentState, MilestoneData


def _create_state(
    session_id: UUID | None = None,
    task_id: UUID | None = None,
    user_id: str = "test-user",
    original_request: str = "Test request",
    milestones: list[MilestoneData] | list[dict[str, Any]] | None = None,
) -> AgentState:
    """Create a mock agent state."""
    state: AgentState = {
        "session_id": session_id or uuid4(),
        "task_id": task_id or uuid4(),
        "user_id": user_id,
        "original_request": original_request,
        "milestones": milestones or [],  # type: ignore[typeddict-item]
    }
    return state


def _create_milestone(
    description: str = "Test milestone",
    status: MilestoneStatus = MilestoneStatus.PASSED,
    worker_output: str = "Test output",
) -> dict[str, Any]:
    """Create a mock milestone dict."""
    return {
        "id": uuid4(),
        "description": description,
        "complexity": TaskComplexity.SIMPLE,
        "acceptance_criteria": "Test criteria",
        "status": status,
        "selected_model": "gpt-4o-mini",
        "generated_prompt": None,
        "worker_output": worker_output,
        "qa_feedback": None,
        "retry_count": 0,
    }


@pytest.fixture
def mock_config():
    """Create mock runnable config."""
    return RunnableConfig(configurable={})


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_repos():
    """Create mock repositories for both ArtifactRepository and TaskRepository."""
    with (
        patch("agent.graph.nodes.task_summary.ArtifactRepository") as MockArtifactRepo,
        patch("agent.graph.nodes.task_summary.TaskRepository") as MockTaskRepo,
    ):
        mock_artifact_repo = MagicMock()
        mock_artifact_repo.get_by_task_id = AsyncMock(return_value=[])
        MockArtifactRepo.return_value = mock_artifact_repo

        mock_task_repo = MagicMock()
        mock_task_repo.save_handover_context = AsyncMock(return_value=None)
        MockTaskRepo.return_value = mock_task_repo

        yield {
            "artifact_repo": mock_artifact_repo,
            "task_repo": mock_task_repo,
            "MockArtifactRepo": MockArtifactRepo,
            "MockTaskRepo": MockTaskRepo,
        }


class TestTaskSummaryNode:
    """Tests for task_summary_node function."""

    async def test_summary_with_no_milestones(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_repos: dict[str, Any],
    ) -> None:
        """Test summary generation with no milestones."""
        state = _create_state(milestones=[])

        result = await task_summary_node(state, mock_config, mock_session)

        assert "task_summary" in result
        summary = result["task_summary"]
        assert summary["milestone_count"] == 0
        assert summary["milestones"] == []
        assert summary["artifact_count"] == 0
        assert summary["artifacts"] == []

    async def test_summary_with_single_milestone(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_repos: dict[str, Any],
    ) -> None:
        """Test summary generation with a single milestone."""
        milestone = _create_milestone(
            description="Create login page",
            worker_output="Created login.html with form",
        )
        state = _create_state(
            original_request="Build a login page",
            milestones=[milestone],
        )

        result = await task_summary_node(state, mock_config, mock_session)

        summary = result["task_summary"]
        assert summary["milestone_count"] == 1
        assert len(summary["milestones"]) == 1
        assert summary["milestones"][0]["description"] == "Create login page"
        assert summary["milestones"][0]["output"] == "Created login.html with form"
        assert summary["milestones"][0]["index"] == 1

    async def test_summary_with_multiple_milestones(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_repos: dict[str, Any],
    ) -> None:
        """Test summary generation with multiple milestones."""
        milestones = [
            _create_milestone(
                description="Design database schema",
                worker_output="Created users table",
            ),
            _create_milestone(
                description="Implement API endpoints",
                worker_output="Created /users endpoint",
            ),
            _create_milestone(
                description="Write unit tests",
                worker_output="Added 10 test cases",
            ),
        ]
        state = _create_state(
            original_request="Build user management system",
            milestones=milestones,
        )

        result = await task_summary_node(state, mock_config, mock_session)

        summary = result["task_summary"]
        assert summary["milestone_count"] == 3
        assert len(summary["milestones"]) == 3

        # Check milestone indices
        assert summary["milestones"][0]["index"] == 1
        assert summary["milestones"][1]["index"] == 2
        assert summary["milestones"][2]["index"] == 3

        # Check descriptions preserved
        assert summary["milestones"][0]["description"] == "Design database schema"
        assert summary["milestones"][1]["description"] == "Implement API endpoints"
        assert summary["milestones"][2]["description"] == "Write unit tests"

    async def test_summary_includes_artifacts(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_repos: dict[str, Any],
    ) -> None:
        """Test summary includes artifact information."""
        milestone = _create_milestone()
        state = _create_state(milestones=[milestone])

        # Create mock artifacts
        mock_artifact_1 = MagicMock()
        mock_artifact_1.path = "src"
        mock_artifact_1.filename = "app.py"
        mock_artifact_1.kind = "python"
        mock_artifact_1.content = "print('hello')"

        mock_artifact_2 = MagicMock()
        mock_artifact_2.path = ""
        mock_artifact_2.filename = "README.md"
        mock_artifact_2.kind = "markdown"
        mock_artifact_2.content = "# Project"

        mock_repos["artifact_repo"].get_by_task_id = AsyncMock(
            return_value=[mock_artifact_1, mock_artifact_2]
        )

        result = await task_summary_node(state, mock_config, mock_session)

        summary = result["task_summary"]
        assert summary["artifact_count"] == 2
        assert len(summary["artifacts"]) == 2

        # Check artifact paths
        assert summary["artifacts"][0]["path"] == "src/app.py"
        assert summary["artifacts"][0]["kind"] == "python"
        assert summary["artifacts"][1]["path"] == "README.md"
        assert summary["artifacts"][1]["kind"] == "markdown"

    async def test_handover_context_generated(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_repos: dict[str, Any],
    ) -> None:
        """Test handover context is generated for next task."""
        milestone = _create_milestone(
            description="Build feature X",
            status=MilestoneStatus.PASSED,
        )
        state = _create_state(
            original_request="Implement feature X",
            milestones=[milestone],
        )

        result = await task_summary_node(state, mock_config, mock_session)

        summary = result["task_summary"]
        assert "handover_context" in summary

        handover = summary["handover_context"]
        assert "## Previous Task Summary" in handover
        assert "Request: Implement feature X" in handover
        assert "### Completed Work (1 milestones):" in handover
        assert "Build feature X" in handover

    async def test_handover_context_includes_artifacts(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_repos: dict[str, Any],
    ) -> None:
        """Test handover context includes artifact list."""
        milestone = _create_milestone()
        state = _create_state(milestones=[milestone])

        mock_artifact = MagicMock()
        mock_artifact.path = "src"
        mock_artifact.filename = "main.py"
        mock_artifact.kind = "python"
        mock_artifact.content = "code"

        mock_repos["artifact_repo"].get_by_task_id = AsyncMock(return_value=[mock_artifact])

        result = await task_summary_node(state, mock_config, mock_session)

        handover = result["task_summary"]["handover_context"]
        assert "### Artifacts Created (1 files):" in handover
        assert "src/main.py (python)" in handover

    async def test_handover_context_saved_to_db(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_repos: dict[str, Any],
    ) -> None:
        """Test handover context is saved to database."""
        task_id = uuid4()
        milestone = _create_milestone()
        state = _create_state(task_id=task_id, milestones=[milestone])

        await task_summary_node(state, mock_config, mock_session)

        # Verify save_handover_context was called
        mock_repos["task_repo"].save_handover_context.assert_called_once()
        call_args = mock_repos["task_repo"].save_handover_context.call_args
        assert call_args[0][0] == task_id
        assert "## Previous Task Summary" in call_args[0][1]

    async def test_handles_exception_gracefully(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_repos: dict[str, Any],
    ) -> None:
        """Test node handles exceptions without failing workflow."""
        state = _create_state(
            original_request="Test request",
            milestones=[_create_milestone()],
        )

        mock_repos["artifact_repo"].get_by_task_id = AsyncMock(
            side_effect=Exception("Database error")
        )

        result = await task_summary_node(state, mock_config, mock_session)

        # Should return empty summary with error info, not raise
        summary = result["task_summary"]
        assert summary["milestone_count"] == 1
        assert summary["milestones"] == []
        assert summary["artifact_count"] == 0
        assert "error" in summary
        assert "Database error" in summary["error"]

    async def test_preserves_original_request(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_repos: dict[str, Any],
    ) -> None:
        """Test original request is preserved in summary."""
        state = _create_state(
            original_request="Build a todo app with React",
            milestones=[],
        )

        result = await task_summary_node(state, mock_config, mock_session)

        assert result["task_summary"]["original_request"] == "Build a todo app with React"

    async def test_milestone_status_included(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_repos: dict[str, Any],
    ) -> None:
        """Test milestone status is included in summary."""
        milestone = _create_milestone(status=MilestoneStatus.PASSED)
        state = _create_state(milestones=[milestone])

        result = await task_summary_node(state, mock_config, mock_session)

        summary = result["task_summary"]
        assert summary["milestones"][0]["status"] == "MilestoneStatus.PASSED"
