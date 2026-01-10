"""Tests for response generation node."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.graph.nodes.response import generate_response_node
from agent.graph.state import AgentState


def _create_state(**kwargs) -> AgentState:
    """Create a mock agent state."""
    return {
        "session_id": kwargs.get("session_id", uuid4()),
        "task_id": kwargs.get("task_id", uuid4()),
        "original_request": kwargs.get("original_request", "Test request"),
        "milestones": kwargs.get("milestones", []),
        "error": kwargs.get("error"),
        "current_milestone_index": kwargs.get("current_milestone_index", 0),
        "qa_retries": kwargs.get("qa_retries", 0),
        "final_response": kwargs.get("final_response"),
        **kwargs,
    }


@pytest.fixture
def mock_config():
    """Create mock runnable config."""
    config = MagicMock()
    config.get = MagicMock(return_value={})
    return config


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_ws_manager():
    """Create mock WebSocket manager."""
    manager = MagicMock()
    manager.broadcast_to_user = AsyncMock()
    return manager


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
            with patch("agent.graph.nodes.response.get_ws_manager") as mock_get_ws:
                mock_get_container.return_value = MagicMock()
                mock_get_ws.return_value = MagicMock()

                result = await generate_response_node(state, mock_config, mock_session)

        assert "final_response" in result
        assert "Task could not be completed" in result["final_response"]
        assert "Task was cancelled" in result["final_response"]

    async def test_response_success(
        self,
        mock_config,
        mock_session,
        mock_container,
        mock_ws_manager,
    ):
        """Test successful response generation."""
        state = _create_state(
            milestones=[{"worker_output": "Here is the code: ```python\nprint('hello')```"}]
        )

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Your code is ready!")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.get_ws_manager", return_value=mock_ws_manager):
                with patch(
                    "agent.graph.nodes.response.ResponderAgent", return_value=mock_responder
                ):
                    with patch(
                        "agent.graph.nodes.response.broadcast_agent_started", new_callable=AsyncMock
                    ):
                        with patch(
                            "agent.graph.nodes.response.broadcast_agent_completed",
                            new_callable=AsyncMock,
                        ):
                            result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Your code is ready!"

    async def test_response_with_artifacts(
        self,
        mock_config,
        mock_session,
        mock_container,
        mock_ws_manager,
    ):
        """Test response generation detects artifacts."""
        state = _create_state(
            milestones=[{"worker_output": "Created file: ```python\nprint('hello')```"}]
        )

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Generated response")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.get_ws_manager", return_value=mock_ws_manager):
                with patch(
                    "agent.graph.nodes.response.ResponderAgent", return_value=mock_responder
                ):
                    with patch(
                        "agent.graph.nodes.response.broadcast_agent_started", new_callable=AsyncMock
                    ):
                        with patch(
                            "agent.graph.nodes.response.broadcast_agent_completed",
                            new_callable=AsyncMock,
                        ):
                            await generate_response_node(state, mock_config, mock_session)

        # Verify has_artifacts was True
        call_kwargs = mock_responder.generate_response.call_args.kwargs
        assert call_kwargs.get("has_artifacts") is True

    async def test_response_no_milestones(
        self,
        mock_config,
        mock_session,
        mock_container,
        mock_ws_manager,
    ):
        """Test response generation with no milestones."""
        state = _create_state(milestones=[])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Response without milestones")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.get_ws_manager", return_value=mock_ws_manager):
                with patch(
                    "agent.graph.nodes.response.ResponderAgent", return_value=mock_responder
                ):
                    with patch(
                        "agent.graph.nodes.response.broadcast_agent_started", new_callable=AsyncMock
                    ):
                        with patch(
                            "agent.graph.nodes.response.broadcast_agent_completed",
                            new_callable=AsyncMock,
                        ):
                            result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Response without milestones"

    async def test_response_exception_fallback(
        self,
        mock_config,
        mock_session,
        mock_container,
        mock_ws_manager,
    ):
        """Test fallback when responder fails."""
        state = _create_state(milestones=[{"worker_output": "Fallback output"}])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(side_effect=Exception("LLM error"))

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.get_ws_manager", return_value=mock_ws_manager):
                with patch(
                    "agent.graph.nodes.response.ResponderAgent", return_value=mock_responder
                ):
                    with patch(
                        "agent.graph.nodes.response.broadcast_agent_started", new_callable=AsyncMock
                    ):
                        result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Fallback output"
        assert result["error"] == "LLM error"
        assert result["error_node"] == "generate_response"

    async def test_response_exception_no_milestones_fallback(
        self,
        mock_config,
        mock_session,
        mock_container,
        mock_ws_manager,
    ):
        """Test fallback when responder fails and no milestones."""
        state = _create_state(milestones=[])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(side_effect=Exception("LLM error"))

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.get_ws_manager", return_value=mock_ws_manager):
                with patch(
                    "agent.graph.nodes.response.ResponderAgent", return_value=mock_responder
                ):
                    with patch(
                        "agent.graph.nodes.response.broadcast_agent_started", new_callable=AsyncMock
                    ):
                        result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Task completed."

    async def test_response_milestone_none_worker_output(
        self,
        mock_config,
        mock_session,
        mock_container,
        mock_ws_manager,
    ):
        """Test response when worker_output is None."""
        state = _create_state(milestones=[{"worker_output": None}])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Response generated")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.get_ws_manager", return_value=mock_ws_manager):
                with patch(
                    "agent.graph.nodes.response.ResponderAgent", return_value=mock_responder
                ):
                    with patch(
                        "agent.graph.nodes.response.broadcast_agent_started", new_callable=AsyncMock
                    ):
                        with patch(
                            "agent.graph.nodes.response.broadcast_agent_completed",
                            new_callable=AsyncMock,
                        ):
                            result = await generate_response_node(state, mock_config, mock_session)

        assert result["final_response"] == "Response generated"

    async def test_broadcasts_agent_events(
        self,
        mock_config,
        mock_session,
        mock_container,
        mock_ws_manager,
    ):
        """Test that agent started and completed events are broadcast."""
        state = _create_state(milestones=[{"worker_output": "output"}])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Response")

        with patch("agent.graph.nodes.response.get_container", return_value=mock_container):
            with patch("agent.graph.nodes.response.get_ws_manager", return_value=mock_ws_manager):
                with patch(
                    "agent.graph.nodes.response.ResponderAgent", return_value=mock_responder
                ):
                    with patch(
                        "agent.graph.nodes.response.broadcast_agent_started", new_callable=AsyncMock
                    ) as mock_started:
                        with patch(
                            "agent.graph.nodes.response.broadcast_agent_completed",
                            new_callable=AsyncMock,
                        ) as mock_completed:
                            await generate_response_node(state, mock_config, mock_session)

        mock_started.assert_called_once()
        mock_completed.assert_called_once()

        # Verify broadcast parameters
        completed_kwargs = mock_completed.call_args.kwargs
        assert completed_kwargs["agent"] == "responder"
        assert "final_response" in completed_kwargs["details"]
