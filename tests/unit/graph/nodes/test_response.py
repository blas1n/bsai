"""Tests for response generation node."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.graph.nodes.response import generate_response_node
from agent.graph.state import AgentState, MilestoneData


def _create_state(
    session_id: UUID | None = None,
    task_id: UUID | None = None,
    user_id: str = "test-user",
    original_request: str = "Test request",
    milestones: list[MilestoneData] | list[dict[str, Any]] | None = None,
    error: str | None = None,
    current_milestone_index: int = 0,
    retry_count: int = 0,
    final_response: str | None = None,
) -> AgentState:
    """Create a mock agent state."""
    state: AgentState = {
        "session_id": session_id or uuid4(),
        "task_id": task_id or uuid4(),
        "user_id": user_id,
        "original_request": original_request,
        "milestones": milestones or [],  # type: ignore[typeddict-item]
        "error": error,
        "current_milestone_index": current_milestone_index,
        "retry_count": retry_count,
        "final_response": final_response,
    }
    return state


@pytest.fixture
def mock_event_bus():
    """Create mock event bus."""
    event_bus = MagicMock()
    event_bus.emit = AsyncMock()
    return event_bus


@pytest.fixture
def mock_config(mock_event_bus):
    """Create mock runnable config."""

    return RunnableConfig(
        configurable={
            "event_bus": mock_event_bus,
        }
    )


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_container():
    """Create mock container with dependencies."""
    container = MagicMock()
    container.llm_client = MagicMock()
    container.router = MagicMock()
    container.prompt_manager = MagicMock()
    return container


class TestGenerateResponseNode:
    """Tests for generate_response_node function."""

    async def test_response_with_error_state(
        self,
        mock_config,
        mock_session,
    ):
        """Test response generation when error exists in state."""
        state = _create_state(error="Task was cancelled")

        with patch("agent.graph.nodes.response.get_container") as mock_get_container:
            mock_get_container.return_value = MagicMock()

            result = await generate_response_node(state, mock_config, mock_session)

        assert "final_response" in result
        assert "Task could not be completed" in result["final_response"]
        assert "Task was cancelled" in result["final_response"]

    async def test_response_success(
        self,
        mock_config,
        mock_session,
        mock_container,
    ):
        """Test successful response generation."""
        state = _create_state(
            milestones=[{"worker_output": "Here is the code: ```python\nprint('hello')```"}]
        )

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Your code is ready!")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Your code is ready!"

    async def test_response_with_artifacts(
        self,
        mock_config,
        mock_session,
        mock_container,
    ):
        """Test response generation detects artifacts."""
        state = _create_state(
            milestones=[{"worker_output": "Created file: ```python\nprint('hello')```"}]
        )

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Generated response")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                await generate_response_node(state, mock_config, mock_session)

        # Verify has_artifacts was True
        call_kwargs = mock_responder.generate_response.call_args.kwargs
        assert call_kwargs.get("has_artifacts") is True

    async def test_response_no_milestones(
        self,
        mock_config,
        mock_session,
        mock_container,
    ):
        """Test response generation with no milestones."""
        state = _create_state(milestones=[])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Response without milestones")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Response without milestones"

    async def test_response_exception_fallback(
        self,
        mock_config,
        mock_session,
        mock_container,
    ):
        """Test fallback when responder fails."""
        state = _create_state(milestones=[{"worker_output": "Fallback output"}])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(side_effect=Exception("LLM error"))

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Fallback output"
        assert result["error"] == "LLM error"
        assert result["error_node"] == "generate_response"

    async def test_response_exception_no_milestones_fallback(
        self,
        mock_config,
        mock_session,
        mock_container,
    ):
        """Test fallback when responder fails and no milestones."""
        state = _create_state(milestones=[])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(side_effect=Exception("LLM error"))

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Task completed."

    async def test_response_milestone_none_worker_output(
        self,
        mock_config,
        mock_session,
        mock_container,
    ):
        """Test response when worker_output is None."""
        state = _create_state(milestones=[{"worker_output": None}])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Response generated")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Response generated"

    async def test_broadcasts_agent_events(
        self,
        mock_config,
        mock_session,
        mock_container,
        mock_event_bus,
    ):
        """Test that agent started and completed events are broadcast."""
        state = _create_state(milestones=[{"worker_output": "output"}])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Response")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                await generate_response_node(state, mock_config, mock_session)

        # Verify event bus emit was called twice (started + completed)
        assert mock_event_bus.emit.call_count == 2

        # Verify completed event
        completed_event = mock_event_bus.emit.call_args_list[1][0][0]
        assert completed_event.agent == "responder"
        assert "final_response" in completed_event.details

    async def test_response_uses_task_summary(
        self,
        mock_config,
        mock_session,
        mock_container,
    ):
        """Test response generation uses task_summary when available."""
        # State with task_summary from task_summary node
        state = _create_state(
            milestones=[
                {"worker_output": "First milestone output"},
                {"worker_output": "Second milestone output"},
            ]
        )
        state["task_summary"] = {
            "milestones": [
                {"description": "First task", "output": "First milestone output"},
                {"description": "Second task", "output": "Second milestone output"},
            ],
            "artifacts": [{"path": "src/app.py", "kind": "python"}],
        }

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Complete response")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Complete response"

        # Verify worker_output includes all milestones
        call_kwargs = mock_responder.generate_response.call_args.kwargs
        worker_output = call_kwargs.get("worker_output", "")
        assert "First task" in worker_output
        assert "Second task" in worker_output
        assert "First milestone output" in worker_output
        assert "Second milestone output" in worker_output

    async def test_response_detects_artifacts_from_task_summary(
        self,
        mock_config,
        mock_session,
        mock_container,
    ):
        """Test has_artifacts is True when task_summary contains artifacts."""
        state = _create_state(milestones=[{"worker_output": "output"}])
        state["task_summary"] = {
            "milestones": [{"description": "Task", "output": "output"}],
            "artifacts": [{"path": "main.py", "kind": "python"}],
        }

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Response")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                await generate_response_node(state, mock_config, mock_session)

        call_kwargs = mock_responder.generate_response.call_args.kwargs
        assert call_kwargs.get("has_artifacts") is True

    async def test_response_no_artifacts_from_task_summary(
        self,
        mock_config,
        mock_session,
        mock_container,
    ):
        """Test has_artifacts is False when task_summary has no artifacts."""
        state = _create_state(milestones=[{"worker_output": "output"}])
        state["task_summary"] = {
            "milestones": [{"description": "Task", "output": "output"}],
            "artifacts": [],  # No artifacts
        }

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Response")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                await generate_response_node(state, mock_config, mock_session)

        call_kwargs = mock_responder.generate_response.call_args.kwargs
        assert call_kwargs.get("has_artifacts") is False

    async def test_response_fallback_without_task_summary(
        self,
        mock_config,
        mock_session,
        mock_container,
    ):
        """Test fallback to last milestone when task_summary is not available."""
        state = _create_state(
            milestones=[
                {"worker_output": "First output"},
                {"worker_output": "Last milestone output with ```code```"},
            ]
        )
        # No task_summary in state

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Fallback response")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.ResponderAgent", return_value=mock_responder):
                await generate_response_node(state, mock_config, mock_session)

        # Should use last milestone's worker_output
        call_kwargs = mock_responder.generate_response.call_args.kwargs
        worker_output = call_kwargs.get("worker_output", "")
        assert worker_output == "Last milestone output with ```code```"
        # Should detect artifacts from code blocks
        assert call_kwargs.get("has_artifacts") is True
