"""Tests for execute worker node with project_plan."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.core.artifact_extractor import ExtractionResult
from agent.graph.nodes.execute import (
    _build_artifacts_context_message,
    _get_artifact_key,
    _prepare_worker_prompt,
    execute_worker_node,
)
from agent.graph.state import AgentState
from agent.llm import LLMResponse, UsageInfo


def _create_state_with_plan(
    worker_output: str | None = None,
    retry_count: int = 0,
    current_qa_feedback: str | None = None,
) -> tuple[AgentState, MagicMock]:
    """Create state with project plan."""
    mock_plan = MagicMock()
    mock_plan.id = uuid4()
    mock_plan.plan_data = {
        "tasks": [
            {
                "id": "T1",
                "description": "Task description",
                "complexity": "SIMPLE",
                "acceptance_criteria": "Must be done",
                "status": "pending",
                "worker_output": worker_output,
            }
        ]
    }

    state = AgentState(
        session_id=uuid4(),
        task_id=uuid4(),
        user_id="test-user-123",
        original_request="Test request",
        project_plan=mock_plan,
        current_task_id="T1",
        retry_count=retry_count,
        context_messages=[],
        current_context_tokens=0,
    )

    if current_qa_feedback:
        state["current_qa_feedback"] = current_qa_feedback

    return state, mock_plan


class TestExecuteWorkerNode:
    """Tests for execute_worker_node with project_plan."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test successful worker execution."""
        state, mock_plan = _create_state_with_plan()

        with (
            patch("agent.graph.nodes.execute.WorkerAgent") as MockWorker,
            patch("agent.graph.nodes.execute.ProjectPlanRepository") as MockPlanRepo,
            patch("agent.graph.nodes.execute.ArtifactRepository") as MockArtifactRepo,
            patch(
                "agent.graph.nodes.execute.extract_artifacts",
                return_value=ExtractionResult(artifacts=[], deleted_paths=[]),
            ),
            patch(
                "agent.graph.nodes.execute.check_task_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_worker = AsyncMock()
            mock_response = LLMResponse(
                content="Task completed successfully",
                usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
                model="gpt-4o-mini",
            )
            mock_worker.execute_milestone.return_value = mock_response
            MockWorker.return_value = mock_worker

            # Setup mock repos
            mock_plan_repo = MagicMock()
            mock_plan_repo.update = AsyncMock()
            MockPlanRepo.return_value = mock_plan_repo

            mock_artifact_repo = MagicMock()
            mock_artifact_repo.get_by_task_id = AsyncMock(return_value=[])
            mock_artifact_repo.get_latest_snapshot = AsyncMock(return_value=[])
            MockArtifactRepo.return_value = mock_artifact_repo

            result = await execute_worker_node(state, mock_config, mock_session)

            assert result["current_output"] == "Task completed successfully"
            assert len(result["context_messages"]) == 2  # user + assistant
            assert result["current_context_tokens"] == 150

    @pytest.mark.asyncio
    async def test_retry_with_feedback(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test worker retry with QA feedback."""
        state, mock_plan = _create_state_with_plan(
            worker_output="Previous output",
            retry_count=1,
            current_qa_feedback="Please fix the error",
        )

        with (
            patch("agent.graph.nodes.execute.WorkerAgent") as MockWorker,
            patch("agent.graph.nodes.execute.ProjectPlanRepository") as MockPlanRepo,
            patch("agent.graph.nodes.execute.ArtifactRepository") as MockArtifactRepo,
            patch(
                "agent.graph.nodes.execute.extract_artifacts",
                return_value=ExtractionResult(artifacts=[], deleted_paths=[]),
            ),
            patch(
                "agent.graph.nodes.execute.check_task_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_worker = AsyncMock()
            mock_response = LLMResponse(
                content="Fixed output",
                usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
                model="gpt-4o-mini",
            )
            mock_worker.retry_with_feedback.return_value = mock_response
            MockWorker.return_value = mock_worker

            # Setup mock repos
            mock_plan_repo = MagicMock()
            mock_plan_repo.update = AsyncMock()
            MockPlanRepo.return_value = mock_plan_repo

            mock_artifact_repo = MagicMock()
            mock_artifact_repo.get_by_task_id = AsyncMock(return_value=[])
            mock_artifact_repo.get_latest_snapshot = AsyncMock(return_value=[])
            MockArtifactRepo.return_value = mock_artifact_repo

            result = await execute_worker_node(state, mock_config, mock_session)

            mock_worker.retry_with_feedback.assert_called_once()
            assert result["current_output"] == "Fixed output"

    @pytest.mark.asyncio
    async def test_no_project_plan_returns_error(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test error handling when no project plan exists."""
        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            user_id="test-user",
            original_request="Test",
        )

        with patch(
            "agent.graph.nodes.execute.check_task_cancelled",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await execute_worker_node(state, mock_config, mock_session)

            assert result["error"] == "No project_plan available"
            assert result["error_node"] == "execute_worker"


class TestHelperFunctions:
    """Tests for helper functions in execute module."""

    def test_get_artifact_key_with_path(self) -> None:
        """Test artifact key generation with path."""
        mock_artifact = MagicMock()
        mock_artifact.path = "src/components"
        mock_artifact.filename = "Button.tsx"

        key = _get_artifact_key(mock_artifact)

        assert key == "src/components/Button.tsx"

    def test_get_artifact_key_no_path(self) -> None:
        """Test artifact key generation without path."""
        mock_artifact = MagicMock()
        mock_artifact.path = ""
        mock_artifact.filename = "README.md"

        key = _get_artifact_key(mock_artifact)

        assert key == "README.md"

    def test_get_artifact_key_none_path(self) -> None:
        """Test artifact key generation with None path."""
        mock_artifact = MagicMock()
        mock_artifact.path = None
        mock_artifact.filename = "config.json"

        key = _get_artifact_key(mock_artifact)

        assert key == "config.json"

    def test_get_artifact_key_strips_slashes(self) -> None:
        """Test artifact key strips leading/trailing slashes from path."""
        mock_artifact = MagicMock()
        mock_artifact.path = "/src/utils/"
        mock_artifact.filename = "helper.py"

        key = _get_artifact_key(mock_artifact)

        assert key == "src/utils/helper.py"

    def test_build_artifacts_context_message_with_artifacts(self) -> None:
        """Test building context message with artifacts."""
        artifact1 = MagicMock()
        artifact1.path = "src"
        artifact1.filename = "main.py"
        artifact1.kind = "py"
        artifact1.content = "print('hello')"

        artifact2 = MagicMock()
        artifact2.path = ""
        artifact2.filename = "README.md"
        artifact2.kind = "md"
        artifact2.content = "# Project"

        message = _build_artifacts_context_message([artifact1, artifact2])

        assert message is not None
        assert message.role == "system"
        assert "Session Files" in message.content
        assert "2 files" in message.content
        assert "src/main.py" in message.content
        assert "README.md" in message.content

    def test_build_artifacts_context_message_empty(self) -> None:
        """Test building context message with no artifacts."""
        message = _build_artifacts_context_message([])

        assert message is None

    def test_prepare_worker_prompt_with_original_request(self) -> None:
        """Test prompt preparation includes original request."""
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test",
            "original_request": "Build a calculator app",
        }
        task = {"description": "Implement add function"}

        prompt = _prepare_worker_prompt(state, task)

        assert "Build a calculator app" in prompt
        assert "Implement add function" in prompt
        assert "Original user request:" in prompt

    def test_prepare_worker_prompt_with_acceptance_criteria(self) -> None:
        """Test prompt includes acceptance criteria."""
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test",
            "original_request": "Request",
        }
        task = {
            "description": "Task description",
            "acceptance_criteria": "Must pass all tests",
        }

        prompt = _prepare_worker_prompt(state, task)

        assert "Must pass all tests" in prompt
        assert "Acceptance criteria:" in prompt
