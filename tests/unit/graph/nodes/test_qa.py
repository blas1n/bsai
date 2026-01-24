"""Tests for QA verification node."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.nodes.qa import verify_qa_node
from agent.graph.state import AgentState, MilestoneData
from agent.llm.schemas import QAOutput


def _make_qa_output(
    decision: str = "PASS",
    feedback: str = "Good",
    plan_viability: str = "VIABLE",
) -> QAOutput:
    """Helper to create QAOutput for tests."""
    return QAOutput(
        decision=decision,
        feedback=feedback,
        issues=[],
        suggestions=[],
        plan_viability=plan_viability,
        plan_viability_reason=None,
        confidence=0.8,
    )


class TestVerifyQaNode:
    """Tests for verify_qa_node."""

    @pytest.mark.asyncio
    async def test_pass_decision(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA pass decision."""
        from agent.core import QADecision

        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output="Good output",
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
            retry_count=0,
        )

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
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
            assert result["milestones"][0]["status"] == MilestoneStatus.PASSED

    @pytest.mark.asyncio
    async def test_fail_decision(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA fail decision."""
        from agent.core import QADecision

        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Must be perfect",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output="Poor output",
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
            retry_count=0,
        )

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (
                QADecision.FAIL,
                "Does not meet criteria",
                _make_qa_output("RETRY", "Does not meet criteria"),
            )
            MockQA.return_value = mock_qa

            result = await verify_qa_node(state, mock_config, mock_session)

            assert result["current_qa_decision"] == "fail"
            assert result["milestones"][0]["status"] == MilestoneStatus.FAILED

    @pytest.mark.asyncio
    async def test_retry_decision(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA retry decision keeps IN_PROGRESS status."""
        from agent.core import QADecision

        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Needs improvement",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output="Partial output",
            qa_feedback=None,
            retry_count=1,
        )

        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            user_id="test-user-123",
            original_request="Test",
            milestones=[milestone],
            current_milestone_index=0,
            retry_count=1,
        )

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
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
            # RETRY keeps IN_PROGRESS status
            assert result["milestones"][0]["status"] == MilestoneStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_cancelled_task(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA returns early when task is cancelled."""
        from agent.db.models.enums import TaskStatus

        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output="Output",
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
            retry_count=0,
        )

        with patch(
            "agent.graph.nodes.qa.check_task_cancelled",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await verify_qa_node(state, mock_config, mock_session)

            assert result["error"] == "Task cancelled by user"
            assert result["error_node"] == "verify_qa"
            assert result["task_status"] == TaskStatus.FAILED
            assert result["workflow_complete"] is True

    @pytest.mark.asyncio
    async def test_no_milestones(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA returns error when no milestones."""
        # Create state without milestones key to test None check
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "user_id": "test-user-123",
            "original_request": "Test",
        }

        with patch(
            "agent.graph.nodes.qa.check_task_cancelled",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await verify_qa_node(state, mock_config, mock_session)

            assert result["error"] == "No milestones available"
            assert result["error_node"] == "verify_qa"

    @pytest.mark.asyncio
    async def test_exception_handling(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
    ) -> None:
        """Test QA handles exceptions gracefully."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output="Output",
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
            retry_count=0,
        )

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
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

        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output="Output",
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
            retry_count=0,
        )

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
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
    async def test_empty_feedback_messages(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Test QA with empty feedback generates appropriate messages."""
        from agent.core import QADecision

        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output="Output",
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
            retry_count=0,
        )

        with (
            patch("agent.graph.nodes.qa.QAAgent") as MockQA,
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (
                QADecision.RETRY,
                "",
                _make_qa_output("RETRY", ""),
            )
            MockQA.return_value = mock_qa

            await verify_qa_node(state, mock_config, mock_session)

            # Check the message for empty feedback from completed event
            completed_event = mock_event_bus.emit.call_args_list[1][0][0]
            assert completed_event.message == "Retry needed"
