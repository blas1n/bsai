"""Tests for QA verification node with project_plan."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.graph.nodes.qa import verify_qa_node
from agent.graph.state import AgentState
from agent.llm.schemas import QAOutput


def _make_qa_output(
    decision: str = "PASS",
    feedback: str = "Good",
    plan_viability: str = "VIABLE",
) -> QAOutput:
    """Helper to create QAOutput for tests.

    Note: QAOutput only supports PASS/RETRY decisions.
    FAIL is set by the system when max retries are exceeded.
    """
    return QAOutput(
        decision=decision,
        feedback=feedback,
        issues=[],
        suggestions=[],
        plan_viability=plan_viability,
        plan_viability_reason=None,
        confidence=0.8,
    )


def _create_state_with_plan(
    worker_output: str = "Good output",
    retry_count: int = 0,
    current_qa_feedback: str | None = None,
    current_output: str | None = None,
) -> AgentState:
    """Create state with project plan."""
    mock_plan = MagicMock()
    mock_plan.plan_data = {
        "tasks": [
            {
                "id": "T1",
                "description": "Task description",
                "complexity": "SIMPLE",
                "acceptance_criteria": "Must be done",
                "status": "in_progress",
                "worker_output": worker_output,
            }
        ]
    }

    state = AgentState(
        session_id=uuid4(),
        task_id=uuid4(),
        user_id="test-user-123",
        original_request="Test",
        project_plan=mock_plan,
        current_task_id="T1",
        retry_count=retry_count,
    )

    if current_qa_feedback:
        state["current_qa_feedback"] = current_qa_feedback
    if current_output:
        state["current_output"] = current_output

    return state


class TestVerifyQaNode:
    """Tests for verify_qa_node with project_plan."""

    @pytest.mark.asyncio
    async def test_pass_decision(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA pass decision."""
        from agent.core import QADecision

        state = _create_state_with_plan(worker_output="Good output")

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.NodeContext.check_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (
                QADecision.PASS,
                "Looks good",
                _make_qa_output("PASS", "Looks good"),
            )
            MockQA.return_value = mock_qa

            result = await verify_qa_node(state, mock_config, mock_session)

            assert result["current_qa_decision"] == "pass"

    @pytest.mark.asyncio
    async def test_retry_decision(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA retry decision."""
        from agent.core import QADecision

        state = _create_state_with_plan(
            worker_output="Partial output",
            retry_count=1,
        )

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.NodeContext.check_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (
                QADecision.RETRY,
                "Need improvements",
                _make_qa_output("RETRY", "Need improvements"),
            )
            MockQA.return_value = mock_qa

            result = await verify_qa_node(state, mock_config, mock_session)

            assert result["current_qa_decision"] == "retry"

    @pytest.mark.asyncio
    async def test_no_project_plan(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA returns error when no project_plan."""
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test-user-123",
            "original_request": "Test",
        }

        with patch(
            "agent.graph.nodes.qa.NodeContext.check_cancelled",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await verify_qa_node(state, mock_config, mock_session)

            assert result["error"] == "No project_plan available"
            assert result["error_node"] == "verify_qa"

    @pytest.mark.asyncio
    async def test_exception_handling(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA handles exceptions gracefully."""
        state = _create_state_with_plan(worker_output="Output")

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.NodeContext.check_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.side_effect = Exception("QA validation failed")
            MockQA.return_value = mock_qa

            result = await verify_qa_node(state, mock_config, mock_session)

            assert result["error"] == "QA validation failed"
            assert result["error_node"] == "verify_qa"

    @pytest.mark.asyncio
    async def test_broadcasts_agent_events(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Test QA broadcasts started and completed events."""
        from agent.core import QADecision

        state = _create_state_with_plan(worker_output="Output")

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.NodeContext.check_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (
                QADecision.PASS,
                "Good!",
                _make_qa_output("PASS", "Good!"),
            )
            MockQA.return_value = mock_qa

            await verify_qa_node(state, mock_config, mock_session)

            # Verify event bus emit was called twice (started + completed)
            assert mock_event_bus.emit.call_count == 2

            # Verify started event
            started_event = mock_event_bus.emit.call_args_list[0][0][0]
            assert started_event.agent == "qa"
            assert started_event.message == "Validating output quality"

            # Verify completed event
            completed_event = mock_event_bus.emit.call_args_list[1][0][0]
            assert completed_event.agent == "qa"
            assert "decision" in completed_event.details

    @pytest.mark.asyncio
    async def test_pass_after_retry_stores_qa_learning(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test that PASS after retry stores QA learning."""
        from agent.core import QADecision

        state = _create_state_with_plan(
            worker_output="Improved output",
            retry_count=1,
            current_qa_feedback="Previous feedback for learning",
            current_output="Previous output",
        )

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.NodeContext.check_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("agent.graph.nodes.qa.store_qa_learning", new_callable=AsyncMock) as mock_store,
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (
                QADecision.PASS,
                "Good!",
                _make_qa_output("PASS", "Good!"),
            )
            MockQA.return_value = mock_qa

            result = await verify_qa_node(state, mock_config, mock_session)

            assert result["current_qa_decision"] == "pass"
            # Verify store_qa_learning was called
            mock_store.assert_called_once()
