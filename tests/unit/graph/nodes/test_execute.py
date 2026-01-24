"""Tests for execute worker node."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.core.artifact_extractor import ExtractionResult
from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.nodes.execute import (
    _build_artifacts_context_message,
    _extract_react_observations,
    _get_artifact_key,
    _prepare_worker_prompt,
    execute_worker_node,
)
from agent.graph.state import AgentState, MilestoneData
from agent.llm import LLMResponse, UsageInfo


class TestExecuteWorkerNode:
    """Tests for execute_worker_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test successful worker execution."""
        with (
            patch("agent.graph.nodes.execute.WorkerAgent") as MockWorker,
            patch("agent.graph.nodes.execute.MilestoneRepository") as MockMilestoneRepo,
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
            mock_milestone_repo = MagicMock()
            mock_milestone_repo.update_llm_usage = AsyncMock()
            mock_milestone_repo.update = AsyncMock()
            MockMilestoneRepo.return_value = mock_milestone_repo

            mock_artifact_repo = MagicMock()
            mock_artifact_repo.get_by_task_id = AsyncMock(return_value=[])
            mock_artifact_repo.get_latest_snapshot = AsyncMock(return_value=[])
            MockArtifactRepo.return_value = mock_artifact_repo

            result = await execute_worker_node(state_with_milestone, mock_config, mock_session)

            assert result["current_output"] == "Task completed successfully"
            assert result["milestones"][0]["worker_output"] == "Task completed successfully"
            assert len(result["context_messages"]) == 2  # user + assistant
            assert result["current_context_tokens"] == 150

    @pytest.mark.asyncio
    async def test_retry_with_feedback(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test worker retry with QA feedback."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output="Previous output",
            qa_feedback=None,
            retry_count=0,
        )

        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            user_id="test-user-123",
            original_request="Test",
            milestones=[milestone],
            current_milestone_index=0,
            retry_count=1,
            current_qa_feedback="Please fix the error",
            context_messages=[],
            current_context_tokens=0,
        )

        with (
            patch("agent.graph.nodes.execute.WorkerAgent") as MockWorker,
            patch("agent.graph.nodes.execute.MilestoneRepository") as MockMilestoneRepo,
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
            mock_milestone_repo = MagicMock()
            mock_milestone_repo.update_llm_usage = AsyncMock()
            mock_milestone_repo.update = AsyncMock()
            MockMilestoneRepo.return_value = mock_milestone_repo

            mock_artifact_repo = MagicMock()
            mock_artifact_repo.get_by_task_id = AsyncMock(return_value=[])
            mock_artifact_repo.get_latest_snapshot = AsyncMock(return_value=[])
            MockArtifactRepo.return_value = mock_artifact_repo

            result = await execute_worker_node(state, mock_config, mock_session)

            mock_worker.retry_with_feedback.assert_called_once()
            assert result["current_output"] == "Fixed output"


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
        state = cast(
            AgentState,
            {
                "current_prompt": None,
                "original_request": "Build a calculator app",
            },
        )
        milestone = cast(
            MilestoneData,
            {
                "description": "Implement add function",
            },
        )

        prompt = _prepare_worker_prompt(state, milestone)

        assert "Build a calculator app" in prompt
        assert "Implement add function" in prompt
        assert "Original user request:" in prompt

    def test_prepare_worker_prompt_uses_current_prompt(self) -> None:
        """Test prompt uses current_prompt over milestone description."""
        state = cast(
            AgentState,
            {
                "current_prompt": "Enhanced prompt from MetaPrompter",
                "original_request": "Short request",
            },
        )
        milestone = cast(
            MilestoneData,
            {
                "description": "Basic description",
            },
        )

        prompt = _prepare_worker_prompt(state, milestone)

        assert "Enhanced prompt from MetaPrompter" in prompt
        assert "Short request" in prompt

    def test_prepare_worker_prompt_already_contains_request(self) -> None:
        """Test prompt doesn't duplicate when already containing request."""
        original = "Build a calculator"
        state = cast(
            AgentState,
            {
                "current_prompt": "Task: Build a calculator - enhanced version",
                "original_request": original,
            },
        )
        milestone = cast(
            MilestoneData,
            {
                "description": "Basic",
            },
        )

        prompt = _prepare_worker_prompt(state, milestone)

        # Should not have "Original user request:" prefix since it's already included
        assert "Original user request:" not in prompt
        assert "Build a calculator" in prompt


class TestExtractReactObservations:
    """Tests for _extract_react_observations helper function."""

    def test_extract_valid_react_output(self) -> None:
        """Test extraction from valid WorkerReActOutput JSON."""
        worker_output = """{
            "explanation": "Task completed",
            "files": [],
            "deleted_files": [],
            "observations": ["Found existing config", "API is rate limited"],
            "discovered_issues": ["Memory leak detected"],
            "suggested_plan_changes": []
        }"""

        result = _extract_react_observations(worker_output)

        assert len(result) == 3
        assert "Found existing config" in result
        assert "API is rate limited" in result
        assert "Memory leak detected" in result

    def test_extract_empty_observations(self) -> None:
        """Test extraction with empty observations and issues."""
        worker_output = """{
            "explanation": "Simple task",
            "files": [],
            "deleted_files": [],
            "observations": [],
            "discovered_issues": [],
            "suggested_plan_changes": []
        }"""

        result = _extract_react_observations(worker_output)

        assert result == []

    def test_extract_only_observations(self) -> None:
        """Test extraction with only observations, no issues."""
        worker_output = """{
            "explanation": "Analysis done",
            "files": [],
            "deleted_files": [],
            "observations": ["Pattern found"],
            "discovered_issues": [],
            "suggested_plan_changes": []
        }"""

        result = _extract_react_observations(worker_output)

        assert result == ["Pattern found"]

    def test_extract_only_discovered_issues(self) -> None:
        """Test extraction with only discovered issues."""
        worker_output = """{
            "explanation": "Found problems",
            "files": [],
            "deleted_files": [],
            "observations": [],
            "discovered_issues": ["Bug in module A"],
            "suggested_plan_changes": []
        }"""

        result = _extract_react_observations(worker_output)

        assert result == ["Bug in module A"]

    def test_extract_invalid_json(self) -> None:
        """Test extraction with invalid JSON returns empty list."""
        worker_output = "This is not JSON, just plain text output"

        result = _extract_react_observations(worker_output)

        assert result == []

    def test_extract_regular_worker_output(self) -> None:
        """Test extraction with regular (non-ReAct) worker output."""
        # Regular worker output doesn't have observations/discovered_issues
        worker_output = """{
            "explanation": "Done",
            "files": [{"path": "test.py", "content": "print(1)", "kind": "py"}],
            "deleted_files": []
        }"""

        result = _extract_react_observations(worker_output)

        # Should return empty since default values are empty lists
        assert result == []

    def test_extract_malformed_json(self) -> None:
        """Test extraction with malformed JSON."""
        worker_output = '{"explanation": "incomplete'

        result = _extract_react_observations(worker_output)

        assert result == []
