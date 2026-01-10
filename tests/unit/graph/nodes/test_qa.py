"""Tests for QA verification node."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.nodes.qa import verify_qa_node
from agent.graph.state import AgentState, MilestoneData


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
            patch("agent.graph.nodes.qa.broadcast_agent_started", new_callable=AsyncMock),
            patch("agent.graph.nodes.qa.broadcast_agent_completed", new_callable=AsyncMock),
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (QADecision.PASS, "Looks good")
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
            patch("agent.graph.nodes.qa.broadcast_agent_started", new_callable=AsyncMock),
            patch("agent.graph.nodes.qa.broadcast_agent_completed", new_callable=AsyncMock),
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (QADecision.FAIL, "Does not meet criteria")
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
            patch("agent.graph.nodes.qa.broadcast_agent_started", new_callable=AsyncMock),
            patch("agent.graph.nodes.qa.broadcast_agent_completed", new_callable=AsyncMock),
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (QADecision.RETRY, "Need improvements")
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
        state = AgentState(
            session_id=uuid4(),
            task_id=uuid4(),
            user_id="test-user-123",
            original_request="Test",
            milestones=None,
            current_milestone_index=None,
            retry_count=0,
        )

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
            patch("agent.graph.nodes.qa.broadcast_agent_started", new_callable=AsyncMock),
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
                "agent.graph.nodes.qa.broadcast_agent_started", new_callable=AsyncMock
            ) as mock_started,
            patch(
                "agent.graph.nodes.qa.broadcast_agent_completed", new_callable=AsyncMock
            ) as mock_completed,
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (QADecision.PASS, "Good!")
            MockQA.return_value = mock_qa

            await verify_qa_node(state, mock_config, mock_session)

            mock_started.assert_called_once()
            mock_completed.assert_called_once()

            # Verify broadcast parameters
            started_kwargs = mock_started.call_args.kwargs
            assert started_kwargs["agent"] == "qa"
            assert started_kwargs["message"] == "Validating output quality"

            completed_kwargs = mock_completed.call_args.kwargs
            assert completed_kwargs["agent"] == "qa"
            assert "decision" in completed_kwargs["details"]

    @pytest.mark.asyncio
    async def test_empty_feedback_messages(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
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
            patch("agent.graph.nodes.qa.broadcast_agent_started", new_callable=AsyncMock),
            patch(
                "agent.graph.nodes.qa.broadcast_agent_completed", new_callable=AsyncMock
            ) as mock_completed,
            patch(
                "agent.graph.nodes.qa.check_task_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (QADecision.RETRY, "")
            MockQA.return_value = mock_qa

            await verify_qa_node(state, mock_config, mock_session)

            # Check the message for empty feedback
            completed_kwargs = mock_completed.call_args.kwargs
            assert completed_kwargs["message"] == "Retry needed"
