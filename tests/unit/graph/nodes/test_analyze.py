"""Tests for analyze node."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from bsai.db.models.enums import TaskStatus
from bsai.graph.nodes.analyze import analyze_task_node
from bsai.graph.state import AgentState
from bsai.llm.schemas import ChatMessage, PlanStatus


def create_mock_project_plan(
    plan_id: str | None = None,
    tasks: list[dict[str, str]] | None = None,
) -> MagicMock:
    """Create a mock ProjectPlan object."""
    mock_plan = MagicMock()
    mock_plan.id = uuid4() if plan_id is None else plan_id
    mock_plan.structure_type = "flat"
    mock_plan.total_tasks = len(tasks) if tasks else 0
    mock_plan.plan_data = {"tasks": tasks or []}
    return mock_plan


class TestAnalyzeTaskNode:
    """Tests for analyze_task_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test successful task analysis."""
        with (
            patch("bsai.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("bsai.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Mock memory context retrieval
            mock_get_memory_context.return_value = ([], "")

            # Create mock ProjectPlan
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "id": "T1",
                        "description": "Setup project",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "Project initialized",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            result = await analyze_task_node(base_state, mock_config, mock_session)

            assert result["project_plan"] == mock_plan
            assert result["current_task_id"] == "T1"
            assert result["task_status"] == TaskStatus.IN_PROGRESS
            assert result["retry_count"] == 0
            assert result["plan_status"] == PlanStatus.DRAFT

    @pytest.mark.asyncio
    async def test_error_handling(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test error handling in analyze_task."""
        with (
            patch("bsai.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("bsai.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Mock memory context retrieval
            mock_get_memory_context.return_value = ([], "")

            mock_architect = AsyncMock()
            mock_architect.create_plan.side_effect = ValueError("LLM error")
            MockArchitect.return_value = mock_architect

            result = await analyze_task_node(base_state, mock_config, mock_session)

            assert result["error"] == "LLM error"
            assert result["error_node"] == "analyze_task"
            assert result["task_status"] == TaskStatus.FAILED
            assert result["workflow_complete"] is True

    @pytest.mark.asyncio
    async def test_with_handover_context(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test task analysis with handover context from previous task."""
        # Add context message with handover context
        handover_msg = ChatMessage(
            role="system",
            content="Context from previous task: User completed setup successfully.",
        )
        state_with_handover = AgentState(**{**base_state, "context_messages": [handover_msg]})

        with (
            patch("bsai.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("bsai.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Mock memory context retrieval with actual context
            mock_get_memory_context.return_value = ([], "Related memory: previous project info")

            # Create mock ProjectPlan
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "id": "T1",
                        "description": "Continue from previous",
                        "complexity": "MODERATE",
                        "acceptance_criteria": "Task completed",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            result = await analyze_task_node(state_with_handover, mock_config, mock_session)

            # Verify architect was called with combined context
            mock_architect.create_plan.assert_called_once()
            call_kwargs = mock_architect.create_plan.call_args[1]
            assert "Context from previous task" in call_kwargs["memory_context"]
            assert "Related memory" in call_kwargs["memory_context"]

            assert result["project_plan"] == mock_plan
            assert result["task_status"] == TaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_with_only_handover_context(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test task analysis with only handover context (no memory context)."""
        handover_msg = ChatMessage(
            role="system",
            content="Context from previous task: User completed phase 1.",
        )
        state_with_handover = AgentState(**{**base_state, "context_messages": [handover_msg]})

        with (
            patch("bsai.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("bsai.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # No memory context, only handover
            mock_get_memory_context.return_value = ([], None)

            # Create mock ProjectPlan
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "id": "T1",
                        "description": "Phase 2",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "Phase 2 done",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            result = await analyze_task_node(state_with_handover, mock_config, mock_session)

            # Verify architect was called with handover context only
            call_kwargs = mock_architect.create_plan.call_args[1]
            assert "Context from previous task" in call_kwargs["memory_context"]

            assert result["project_plan"] == mock_plan

    @pytest.mark.asyncio
    async def test_empty_tasks_list(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test handling empty tasks list."""
        with (
            patch("bsai.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("bsai.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            mock_get_memory_context.return_value = ([], "")

            # Create mock ProjectPlan with empty tasks
            mock_plan = create_mock_project_plan(tasks=[])

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            result = await analyze_task_node(base_state, mock_config, mock_session)

            assert result["project_plan"] == mock_plan
            assert result["current_task_id"] is None
            assert result["task_status"] == TaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_multiple_tasks(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test handling multiple tasks in plan."""
        with (
            patch("bsai.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("bsai.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            mock_get_memory_context.return_value = ([], "")

            # Create mock ProjectPlan with 3 tasks
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "id": "T1",
                        "description": "Task 1",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "Done 1",
                    },
                    {
                        "id": "T2",
                        "description": "Task 2",
                        "complexity": "MODERATE",
                        "acceptance_criteria": "Done 2",
                        "depends_on": ["T1"],
                    },
                    {
                        "id": "T3",
                        "description": "Task 3",
                        "complexity": "COMPLEX",
                        "acceptance_criteria": "Done 3",
                        "depends_on": ["T1", "T2"],
                    },
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            result = await analyze_task_node(base_state, mock_config, mock_session)

            assert result["project_plan"] == mock_plan
            # First task ID should be set
            assert result["current_task_id"] == "T1"
            assert result["task_status"] == TaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_with_only_memory_context(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test task analysis with only memory context (no handover)."""
        with (
            patch("bsai.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("bsai.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Only memory context, no handover
            mock_get_memory_context.return_value = (
                [{"content": "memory1"}],
                "Relevant memory context here",
            )

            # Create mock ProjectPlan
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "id": "T1",
                        "description": "Memory-informed task",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "Task done",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            result = await analyze_task_node(base_state, mock_config, mock_session)

            # Verify architect was called with memory context
            call_kwargs = mock_architect.create_plan.call_args[1]
            assert call_kwargs["memory_context"] == "Relevant memory context here"

            assert result["project_plan"] == mock_plan

    @pytest.mark.asyncio
    async def test_broadcasts_agent_events(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
        mock_event_bus: MagicMock,
    ) -> None:
        """Test that agent started and completed events are broadcast."""
        with (
            patch("bsai.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("bsai.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            mock_get_memory_context.return_value = ([], "")

            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "id": "T1",
                        "description": "Task 1",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "Done",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            await analyze_task_node(base_state, mock_config, mock_session)

            # Verify event bus emit was called twice (started + completed)
            assert mock_event_bus.emit.call_count == 2

            # Verify started event
            started_event = mock_event_bus.emit.call_args_list[0][0][0]
            assert started_event.agent == "architect"

            # Verify completed event
            completed_event = mock_event_bus.emit.call_args_list[1][0][0]
            assert completed_event.agent == "architect"
            assert "plan_id" in completed_event.details
