"""Tests for analyze node."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import TaskComplexity, TaskStatus
from agent.graph.nodes.analyze import analyze_task_node
from agent.graph.state import AgentState
from agent.llm.schemas import ChatMessage, PlanStatus


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
            patch("agent.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Mock memory context retrieval
            mock_get_memory_context.return_value = ([], "")

            # Create mock ProjectPlan
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "description": "Setup project",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "Project initialized",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            mock_repo = AsyncMock()
            mock_db_milestone = MagicMock()
            mock_db_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = []  # No existing milestones
            mock_repo.create.return_value = mock_db_milestone
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(base_state, mock_config, mock_session)

            assert len(result["milestones"]) == 1
            assert result["current_milestone_index"] == 0
            assert result["task_status"] == TaskStatus.IN_PROGRESS
            assert result["retry_count"] == 0
            assert result["project_plan"] == mock_plan
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
            patch("agent.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Mock memory context retrieval
            mock_get_memory_context.return_value = ([], "")

            # Mock milestone repo for cleanup check (no existing milestones)
            mock_repo = AsyncMock()
            mock_repo.get_by_task_id.return_value = []
            MockMilestoneRepo.return_value = mock_repo

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
            patch("agent.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # Mock memory context retrieval with actual context
            mock_get_memory_context.return_value = ([], "Related memory: previous project info")

            # Create mock ProjectPlan
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "description": "Continue from previous",
                        "complexity": "MODERATE",
                        "acceptance_criteria": "Task completed",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            mock_repo = AsyncMock()
            mock_db_milestone = MagicMock()
            mock_db_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = []
            mock_repo.create.return_value = mock_db_milestone
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(state_with_handover, mock_config, mock_session)

            # Verify architect was called with combined context
            mock_architect.create_plan.assert_called_once()
            call_kwargs = mock_architect.create_plan.call_args[1]
            assert "Context from previous task" in call_kwargs["memory_context"]
            assert "Related memory" in call_kwargs["memory_context"]

            assert len(result["milestones"]) == 1
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
            patch("agent.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            # No memory context, only handover
            mock_get_memory_context.return_value = ([], None)

            # Create mock ProjectPlan with lowercase complexity string
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "description": "Phase 2",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "Phase 2 done",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            mock_repo = AsyncMock()
            mock_db_milestone = MagicMock()
            mock_db_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = []
            mock_repo.create.return_value = mock_db_milestone
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(state_with_handover, mock_config, mock_session)

            # Verify architect was called with handover context only
            call_kwargs = mock_architect.create_plan.call_args[1]
            assert "Context from previous task" in call_kwargs["memory_context"]

            assert len(result["milestones"]) == 1

    @pytest.mark.asyncio
    async def test_complexity_string_conversion(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test complexity string is converted to TaskComplexity enum."""
        with (
            patch("agent.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            mock_get_memory_context.return_value = ([], "")

            # Create mock ProjectPlan with COMPLEX complexity
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "description": "Complex task",
                        "complexity": "COMPLEX",
                        "acceptance_criteria": "Task done",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            mock_repo = AsyncMock()
            mock_db_milestone = MagicMock()
            mock_db_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = []
            mock_repo.create.return_value = mock_db_milestone
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(base_state, mock_config, mock_session)

            assert len(result["milestones"]) == 1
            assert result["milestones"][0]["complexity"] == TaskComplexity.COMPLEX

    @pytest.mark.asyncio
    async def test_milestone_missing_db_id_fallback(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test milestone creation with multiple tasks."""
        with (
            patch("agent.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            mock_get_memory_context.return_value = ([], "")

            # Create mock ProjectPlan with 2 tasks
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "description": "Task 1",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "Done 1",
                    },
                    {
                        "description": "Task 2",
                        "complexity": "MODERATE",
                        "acceptance_criteria": "Done 2",
                    },
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            mock_repo = AsyncMock()
            # Create returns different IDs for each milestone
            mock_milestone_1 = MagicMock()
            mock_milestone_1.id = uuid4()
            mock_milestone_2 = MagicMock()
            mock_milestone_2.id = uuid4()
            mock_repo.get_by_task_id.return_value = []
            mock_repo.create.side_effect = [mock_milestone_1, mock_milestone_2]
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(base_state, mock_config, mock_session)

            # Should create 2 milestones with proper IDs
            assert len(result["milestones"]) == 2
            assert result["milestones"][0]["id"] == mock_milestone_1.id
            assert result["milestones"][1]["id"] == mock_milestone_2.id

    @pytest.mark.asyncio
    async def test_with_existing_milestones(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test task analysis with existing milestones from previous tasks."""
        with (
            patch("agent.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
        ):
            mock_get_memory_context.return_value = ([], "")

            # Create mock ProjectPlan
            mock_plan = create_mock_project_plan(
                tasks=[
                    {
                        "description": "New task",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "New task done",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            mock_repo = AsyncMock()
            mock_db_milestone = MagicMock()
            mock_db_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = []
            mock_repo.create.return_value = mock_db_milestone
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(state_with_milestone, mock_config, mock_session)

            # Should have 2 milestones: 1 existing + 1 new
            assert len(result["milestones"]) == 2
            # Current index should point to first new milestone
            assert result["current_milestone_index"] == 1

    @pytest.mark.asyncio
    async def test_with_only_memory_context(
        self,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test task analysis with only memory context (no handover)."""
        with (
            patch("agent.graph.nodes.analyze.ArchitectAgent") as MockArchitect,
            patch("agent.graph.nodes.analyze.MilestoneRepository") as MockMilestoneRepo,
            patch("agent.graph.nodes.analyze.get_memory_context") as mock_get_memory_context,
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
                        "description": "Memory-informed task",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "Task done",
                    }
                ]
            )

            mock_architect = AsyncMock()
            mock_architect.create_plan.return_value = mock_plan
            MockArchitect.return_value = mock_architect

            mock_repo = AsyncMock()
            mock_db_milestone = MagicMock()
            mock_db_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = []
            mock_repo.create.return_value = mock_db_milestone
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(base_state, mock_config, mock_session)

            # Verify architect was called with memory context
            call_kwargs = mock_architect.create_plan.call_args[1]
            assert call_kwargs["memory_context"] == "Relevant memory context here"

            assert result["memory_context"] == "Relevant memory context here"
            assert result["relevant_memories"] == [{"content": "memory1"}]


class TestConvertPlanToMilestones:
    """Tests for _convert_plan_to_milestones helper function."""

    def test_convert_empty_plan(self) -> None:
        """Test converting empty plan."""
        from agent.graph.nodes.analyze import _convert_plan_to_milestones

        mock_plan = create_mock_project_plan(tasks=[])
        result = _convert_plan_to_milestones(mock_plan)
        assert result == []

    def test_convert_plan_with_tasks(self) -> None:
        """Test converting plan with tasks."""
        from agent.graph.nodes.analyze import _convert_plan_to_milestones

        mock_plan = create_mock_project_plan(
            tasks=[
                {
                    "description": "Task 1",
                    "complexity": "SIMPLE",
                    "acceptance_criteria": "Done 1",
                },
                {
                    "description": "Task 2",
                    "complexity": "MODERATE",
                    "acceptance_criteria": "Done 2",
                },
            ]
        )

        result = _convert_plan_to_milestones(mock_plan)

        assert len(result) == 2
        assert result[0]["description"] == "Task 1"
        assert result[0]["complexity"] == TaskComplexity.SIMPLE
        assert result[1]["description"] == "Task 2"
        assert result[1]["complexity"] == TaskComplexity.MODERATE

    def test_convert_plan_with_invalid_complexity(self) -> None:
        """Test converting plan with invalid complexity defaults to MODERATE."""
        from agent.graph.nodes.analyze import _convert_plan_to_milestones

        mock_plan = create_mock_project_plan(
            tasks=[
                {
                    "description": "Task with invalid complexity",
                    "complexity": "INVALID",
                    "acceptance_criteria": "Done",
                },
            ]
        )

        result = _convert_plan_to_milestones(mock_plan)

        assert len(result) == 1
        assert result[0]["complexity"] == TaskComplexity.MODERATE
