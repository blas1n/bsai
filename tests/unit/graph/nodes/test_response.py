"""Tests for response generation node with project_plan."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from bsai.graph.nodes.response import generate_response_node
from bsai.graph.state import AgentState


def _create_state_with_plan(
    task_outputs: list[tuple[str, str]] | None = None,
    error: str | None = None,
    failure_context: dict | None = None,
) -> AgentState:
    """Create state with project plan.

    Args:
        task_outputs: List of (description, worker_output) tuples
        error: Error message if any
        failure_context: Failure context for failure reports
    """
    tasks = []
    if task_outputs:
        for i, (desc, output) in enumerate(task_outputs):
            tasks.append(
                {
                    "id": f"T{i+1}",
                    "description": desc,
                    "status": "completed",
                    "worker_output": output,
                }
            )

    mock_plan = MagicMock()
    mock_plan.plan_data = {"tasks": tasks}

    state = AgentState(
        session_id=uuid4(),
        task_id=uuid4(),
        user_id="test-user",
        original_request="Test request",
        project_plan=mock_plan,
    )

    if error:
        state["error"] = error
    if failure_context:
        state["failure_context"] = failure_context

    return state


@pytest.fixture
def local_mock_event_bus():
    """Create mock event bus."""
    event_bus = MagicMock()
    event_bus.emit = AsyncMock()
    return event_bus


@pytest.fixture
def local_mock_container():
    """Create mock container with dependencies."""
    container = MagicMock()
    container.llm_client = MagicMock()
    container.router = MagicMock()
    container.prompt_manager = MagicMock()
    return container


@pytest.fixture
def local_mock_config(local_mock_event_bus, local_mock_container):
    """Create mock runnable config with all required dependencies."""
    return RunnableConfig(
        configurable={
            "event_bus": local_mock_event_bus,
            "container": local_mock_container,
        }
    )


@pytest.fixture
def local_mock_session():
    """Create mock database session."""
    return AsyncMock()


class TestGenerateResponseNode:
    """Tests for generate_response_node with project_plan."""

    @pytest.mark.asyncio
    async def test_response_with_error_state(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
    ) -> None:
        """Test response generation when error exists in state."""
        state = _create_state_with_plan(error="Task was cancelled")

        result = await generate_response_node(state, local_mock_config, local_mock_session)

        assert "final_response" in result
        assert "Task could not be completed" in result["final_response"]
        assert "Task was cancelled" in result["final_response"]

    @pytest.mark.asyncio
    async def test_response_success(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
        local_mock_container: MagicMock,
    ) -> None:
        """Test successful response generation."""
        state = _create_state_with_plan(
            task_outputs=[("Task 1", "Here is the code: ```python\nprint('hello')```")]
        )

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Your code is ready!")

        with patch("bsai.graph.nodes.response.ResponderAgent", return_value=mock_responder):
            result = await generate_response_node(state, local_mock_config, local_mock_session)

        assert result["final_response"] == "Your code is ready!"

    @pytest.mark.asyncio
    async def test_response_with_artifacts(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
        local_mock_container: MagicMock,
    ) -> None:
        """Test response generation detects artifacts."""
        state = _create_state_with_plan(
            task_outputs=[("Task 1", "Created file: ```python\nprint('hello')```")]
        )

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Generated response")

        with patch("bsai.graph.nodes.response.ResponderAgent", return_value=mock_responder):
            await generate_response_node(state, local_mock_config, local_mock_session)

        # Verify has_artifacts was True
        call_kwargs = mock_responder.generate_response.call_args.kwargs
        assert call_kwargs.get("has_artifacts") is True

    @pytest.mark.asyncio
    async def test_response_no_tasks(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
        local_mock_container: MagicMock,
    ) -> None:
        """Test response generation with no tasks."""
        state = _create_state_with_plan(task_outputs=[])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Response without tasks")

        with patch("bsai.graph.nodes.response.ResponderAgent", return_value=mock_responder):
            result = await generate_response_node(state, local_mock_config, local_mock_session)

        assert result["final_response"] == "Response without tasks"

    @pytest.mark.asyncio
    async def test_response_exception_fallback(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
        local_mock_container: MagicMock,
    ) -> None:
        """Test fallback when responder fails."""
        state = _create_state_with_plan(task_outputs=[("Task 1", "Fallback output")])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(side_effect=Exception("LLM error"))

        with patch("bsai.graph.nodes.response.ResponderAgent", return_value=mock_responder):
            result = await generate_response_node(state, local_mock_config, local_mock_session)

        # Fallback contains worker output
        assert "Task 1" in result["final_response"]
        assert result["error"] == "LLM error"
        assert result["error_node"] == "generate_response"

    @pytest.mark.asyncio
    async def test_response_exception_no_tasks_fallback(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
        local_mock_container: MagicMock,
    ) -> None:
        """Test fallback when responder fails and no tasks."""
        state = _create_state_with_plan(task_outputs=[])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(side_effect=Exception("LLM error"))

        with patch("bsai.graph.nodes.response.ResponderAgent", return_value=mock_responder):
            result = await generate_response_node(state, local_mock_config, local_mock_session)

        assert result["final_response"] == "Task completed."

    @pytest.mark.asyncio
    async def test_broadcasts_agent_events(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
        local_mock_container: MagicMock,
        local_mock_event_bus: MagicMock,
    ) -> None:
        """Test that agent started and completed events are broadcast."""
        state = _create_state_with_plan(task_outputs=[("Task 1", "output")])

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Response")

        with patch("bsai.graph.nodes.response.ResponderAgent", return_value=mock_responder):
            await generate_response_node(state, local_mock_config, local_mock_session)

        # Verify event bus emit was called twice (started + completed)
        assert local_mock_event_bus.emit.call_count == 2

        # Verify completed event
        completed_event = local_mock_event_bus.emit.call_args_list[1][0][0]
        assert completed_event.agent == "responder"
        assert "final_response" in completed_event.details

    @pytest.mark.asyncio
    async def test_response_combines_multiple_task_outputs(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
        local_mock_container: MagicMock,
    ) -> None:
        """Test response generation combines outputs from multiple tasks."""
        state = _create_state_with_plan(
            task_outputs=[
                ("First task", "First task output"),
                ("Second task", "Second task output"),
            ]
        )

        mock_responder = MagicMock()
        mock_responder.generate_response = AsyncMock(return_value="Complete response")

        with patch("bsai.graph.nodes.response.ResponderAgent", return_value=mock_responder):
            await generate_response_node(state, local_mock_config, local_mock_session)

        # Verify worker_output includes all tasks
        call_kwargs = mock_responder.generate_response.call_args.kwargs
        worker_output = call_kwargs.get("worker_output", "")
        assert "First task" in worker_output
        assert "Second task" in worker_output
        assert "First task output" in worker_output
        assert "Second task output" in worker_output

    @pytest.mark.asyncio
    async def test_response_with_failure_context(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
        local_mock_container: MagicMock,
        local_mock_event_bus: MagicMock,
    ) -> None:
        """Test response generation with failure context."""
        state = _create_state_with_plan(
            task_outputs=[("Step 1", "Partial output")],
            failure_context={
                "attempted_milestones": [
                    {"description": "Step 1", "status": "passed"},
                    {"description": "Step 2", "status": "failed"},
                ],
                "final_error": "Max retries exceeded",
            },
        )

        mock_responder = MagicMock()
        mock_responder.generate_failure_report = AsyncMock(return_value="Failure report generated")

        with patch("bsai.graph.nodes.response.ResponderAgent", return_value=mock_responder):
            result = await generate_response_node(state, local_mock_config, local_mock_session)

        assert result["final_response"] == "Failure report generated"
        mock_responder.generate_failure_report.assert_called_once()

    @pytest.mark.asyncio
    async def test_response_failure_context_emits_event(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
        local_mock_container: MagicMock,
        local_mock_event_bus: MagicMock,
    ) -> None:
        """Test that failure report generation emits completed event."""
        state = _create_state_with_plan(
            failure_context={
                "attempted_milestones": [],
                "final_error": "Error",
            }
        )

        mock_responder = MagicMock()
        mock_responder.generate_failure_report = AsyncMock(return_value="Failure report")

        with patch("bsai.graph.nodes.response.ResponderAgent", return_value=mock_responder):
            await generate_response_node(state, local_mock_config, local_mock_session)

        # Verify event was emitted
        assert local_mock_event_bus.emit.call_count == 1
        event = local_mock_event_bus.emit.call_args_list[0][0][0]
        assert event.agent == "responder"
        assert event.details.get("is_failure_report") is True

    @pytest.mark.asyncio
    async def test_response_failure_context_exception(
        self,
        local_mock_config: RunnableConfig,
        local_mock_session: AsyncMock,
        local_mock_container: MagicMock,
    ) -> None:
        """Test fallback when failure report generation fails."""
        state = _create_state_with_plan(
            error="Original error",
            failure_context={
                "attempted_milestones": [],
                "final_error": "Some error",
            },
        )

        mock_responder = MagicMock()
        mock_responder.generate_failure_report = AsyncMock(side_effect=Exception("LLM failure"))

        with patch("bsai.graph.nodes.response.ResponderAgent", return_value=mock_responder):
            result = await generate_response_node(state, local_mock_config, local_mock_session)

        assert "Task could not be completed" in result["final_response"]
        assert "Original error" in result["final_response"]
