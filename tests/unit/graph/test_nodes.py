"""Tests for workflow node functions."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.graph.nodes import (
    advance_node,
    analyze_task_node,
    check_context_node,
    execute_worker_node,
    generate_prompt_node,
    select_llm_node,
    summarize_node,
    verify_qa_node,
)
from agent.graph.state import AgentState, MilestoneData
from agent.llm import ChatMessage, LLMModel, LLMResponse, UsageInfo


@pytest.fixture
def mock_container() -> MagicMock:
    """Create mock container with all dependencies."""
    container = MagicMock()
    container.llm_client = MagicMock()
    container.router = MagicMock()
    container.prompt_manager = MagicMock()

    container.router.select_model.return_value = LLMModel(
        name="gpt-4o-mini",
        provider="openai",
        input_price_per_1k=Decimal("0.00015"),
        output_price_per_1k=Decimal("0.0006"),
        context_window=128000,
        supports_streaming=True,
    )

    return container


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def base_state() -> AgentState:
    """Create base state for tests."""
    return AgentState(
        session_id=uuid4(),
        task_id=uuid4(),
        original_request="Build a web scraper",
        task_status=TaskStatus.PENDING,
        milestones=[],
        current_milestone_index=0,
        retry_count=0,
        context_messages=[],
        current_context_tokens=0,
        max_context_tokens=100000,
        needs_compression=False,
        workflow_complete=False,
        should_continue=True,
    )


@pytest.fixture
def state_with_milestone(base_state: AgentState) -> AgentState:
    """Create state with a milestone."""
    milestone = MilestoneData(
        id=uuid4(),
        description="Setup project",
        complexity=TaskComplexity.SIMPLE,
        acceptance_criteria="Project initialized",
        status=MilestoneStatus.PENDING,
        selected_model=None,
        generated_prompt=None,
        worker_output=None,
        qa_feedback=None,
        retry_count=0,
    )
    # Create a copy of base_state and override milestones
    state = dict(base_state)
    state["milestones"] = [milestone]
    return AgentState(**state)  # type: ignore[misc]


class TestAnalyzeTaskNode:
    """Tests for analyze_task_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_container: MagicMock,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test successful task analysis."""
        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.ConductorAgent") as MockConductor,
            patch("agent.graph.nodes.MilestoneRepository") as MockMilestoneRepo,
        ):
            mock_conductor = AsyncMock()
            mock_conductor.analyze_and_plan.return_value = [
                {
                    "description": "Setup project",
                    "complexity": TaskComplexity.SIMPLE,
                    "acceptance_criteria": "Project initialized",
                }
            ]
            MockConductor.return_value = mock_conductor

            mock_repo = AsyncMock()
            mock_milestone = MagicMock()
            mock_milestone.id = uuid4()
            mock_repo.get_by_task_id.return_value = [mock_milestone]
            MockMilestoneRepo.return_value = mock_repo

            result = await analyze_task_node(base_state, mock_session)

            assert len(result["milestones"]) == 1
            assert result["current_milestone_index"] == 0
            assert result["task_status"] == TaskStatus.IN_PROGRESS
            assert result["retry_count"] == 0

    @pytest.mark.asyncio
    async def test_error_handling(
        self,
        mock_container: MagicMock,
        mock_session: AsyncMock,
        base_state: AgentState,
    ) -> None:
        """Test error handling in analyze_task."""
        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.ConductorAgent") as MockConductor,
        ):
            mock_conductor = AsyncMock()
            mock_conductor.analyze_and_plan.side_effect = ValueError("LLM error")
            MockConductor.return_value = mock_conductor

            result = await analyze_task_node(base_state, mock_session)

            assert result["error"] == "LLM error"
            assert result["error_node"] == "analyze_task"
            assert result["task_status"] == TaskStatus.FAILED
            assert result["workflow_complete"] is True


class TestSelectLlmNode:
    """Tests for select_llm_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_container: MagicMock,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test successful LLM selection."""
        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.ConductorAgent") as MockConductor,
        ):
            mock_conductor = AsyncMock()
            mock_conductor.select_model_for_milestone.return_value = "gpt-4o-mini"
            MockConductor.return_value = mock_conductor

            result = await select_llm_node(state_with_milestone, mock_session)

            assert result["milestones"][0]["selected_model"] == "gpt-4o-mini"
            assert result["milestones"][0]["status"] == MilestoneStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_error_handling(
        self,
        mock_container: MagicMock,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test error handling in select_llm."""
        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.ConductorAgent") as MockConductor,
        ):
            mock_conductor = AsyncMock()
            mock_conductor.select_model_for_milestone.side_effect = ValueError("Model not found")
            MockConductor.return_value = mock_conductor

            result = await select_llm_node(state_with_milestone, mock_session)

            assert result["error"] == "Model not found"
            assert result["error_node"] == "select_llm"


class TestGeneratePromptNode:
    """Tests for generate_prompt_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_container: MagicMock,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test successful prompt generation."""
        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.MetaPrompterAgent") as MockMetaPrompter,
        ):
            mock_mp = AsyncMock()
            mock_mp.generate_prompt.return_value = "Optimized prompt for task"
            MockMetaPrompter.return_value = mock_mp

            result = await generate_prompt_node(state_with_milestone, mock_session)

            assert result["current_prompt"] == "Optimized prompt for task"
            assert result["milestones"][0]["generated_prompt"] == "Optimized prompt for task"


class TestExecuteWorkerNode:
    """Tests for execute_worker_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_container: MagicMock,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test successful worker execution."""
        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.WorkerAgent") as MockWorker,
        ):
            mock_worker = AsyncMock()
            mock_response = LLMResponse(
                content="Task completed successfully",
                usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
                model="gpt-4o-mini",
            )
            mock_worker.execute_milestone.return_value = mock_response
            MockWorker.return_value = mock_worker

            result = await execute_worker_node(state_with_milestone, mock_session)

            assert result["current_output"] == "Task completed successfully"
            assert result["milestones"][0]["worker_output"] == "Task completed successfully"
            assert len(result["context_messages"]) == 2  # user + assistant
            assert result["current_context_tokens"] == 150

    @pytest.mark.asyncio
    async def test_retry_with_feedback(
        self,
        mock_container: MagicMock,
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

        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "original_request": "Test",
            "milestones": [milestone],
            "current_milestone_index": 0,
            "retry_count": 1,
            "current_qa_feedback": "Please fix the error",
            "context_messages": [],
            "current_context_tokens": 0,
        }

        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.WorkerAgent") as MockWorker,
        ):
            mock_worker = AsyncMock()
            mock_response = LLMResponse(
                content="Fixed output",
                usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
                model="gpt-4o-mini",
            )
            mock_worker.retry_with_feedback.return_value = mock_response
            MockWorker.return_value = mock_worker

            result = await execute_worker_node(state, mock_session)

            mock_worker.retry_with_feedback.assert_called_once()
            assert result["current_output"] == "Fixed output"


class TestVerifyQaNode:
    """Tests for verify_qa_node."""

    @pytest.mark.asyncio
    async def test_pass_decision(
        self,
        mock_container: MagicMock,
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

        state: AgentState = {
            "milestones": [milestone],
            "current_milestone_index": 0,
            "retry_count": 0,
        }

        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.QAAgent") as MockQA,
        ):
            mock_qa = AsyncMock()
            mock_qa.validate_output.return_value = (QADecision.PASS, "Looks good")
            MockQA.return_value = mock_qa

            result = await verify_qa_node(state, mock_session)

            assert result["current_qa_decision"] == "pass"
            assert result["milestones"][0]["status"] == MilestoneStatus.PASSED


class TestCheckContextNode:
    """Tests for check_context_node."""

    @pytest.mark.asyncio
    async def test_needs_compression(
        self,
        mock_container: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        """Test context check when compression is needed."""
        state: AgentState = {
            "current_context_tokens": 90000,
            "max_context_tokens": 100000,
        }

        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.SummarizerAgent") as MockSummarizer,
        ):
            mock_summarizer = MagicMock()
            mock_summarizer.should_compress.return_value = True
            MockSummarizer.return_value = mock_summarizer

            result = await check_context_node(state, mock_session)

            assert result["needs_compression"] is True

    @pytest.mark.asyncio
    async def test_no_compression_needed(
        self,
        mock_container: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        """Test context check when compression is not needed."""
        state: AgentState = {
            "current_context_tokens": 10000,
            "max_context_tokens": 100000,
        }

        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.SummarizerAgent") as MockSummarizer,
        ):
            mock_summarizer = MagicMock()
            mock_summarizer.should_compress.return_value = False
            MockSummarizer.return_value = mock_summarizer

            result = await check_context_node(state, mock_session)

            assert result["needs_compression"] is False


class TestSummarizeNode:
    """Tests for summarize_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_container: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        """Test successful context summarization."""
        state: AgentState = {
            "session_id": uuid4(),
            "task_id": uuid4(),
            "context_messages": [
                ChatMessage(role="user", content="First message"),
                ChatMessage(role="assistant", content="First response"),
                ChatMessage(role="user", content="Second message"),
                ChatMessage(role="assistant", content="Second response"),
            ],
            "current_context_tokens": 90000,
            "max_context_tokens": 100000,
        }

        with (
            patch("agent.graph.nodes.get_container", return_value=mock_container),
            patch("agent.graph.nodes.SummarizerAgent") as MockSummarizer,
        ):
            mock_summarizer = AsyncMock()
            remaining = [ChatMessage(role="assistant", content="Second response")]
            mock_summarizer.compress_context.return_value = ("Context summary", remaining)
            MockSummarizer.return_value = mock_summarizer

            result = await summarize_node(state, mock_session)

            assert result["context_summary"] == "Context summary"
            assert result["needs_compression"] is False
            assert len(result["context_messages"]) == 2  # summary + remaining


class TestAdvanceNode:
    """Tests for advance_node."""

    @pytest.mark.asyncio
    async def test_retry_decision(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test advance with retry decision."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.IN_PROGRESS,
            selected_model=None,
            generated_prompt=None,
            worker_output=None,
            qa_feedback=None,
            retry_count=0,
        )

        state: AgentState = {
            "milestones": [milestone],
            "current_milestone_index": 0,
            "current_qa_decision": "retry",
            "retry_count": 0,
        }

        result = await advance_node(state, mock_session)

        assert result["retry_count"] == 1
        assert result["should_continue"] is False
        assert result.get("current_qa_decision") is None

    @pytest.mark.asyncio
    async def test_fail_decision(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test advance with fail decision."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.FAILED,
            selected_model=None,
            generated_prompt=None,
            worker_output=None,
            qa_feedback=None,
            retry_count=0,
        )

        state: AgentState = {
            "milestones": [milestone],
            "current_milestone_index": 0,
            "current_qa_decision": "fail",
        }

        result = await advance_node(state, mock_session)

        assert result["task_status"] == TaskStatus.FAILED
        assert result["workflow_complete"] is True

    @pytest.mark.asyncio
    async def test_pass_to_next_milestone(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test advancing to next milestone on pass."""
        milestones = [
            MilestoneData(
                id=uuid4(),
                description="Task 1",
                complexity=TaskComplexity.SIMPLE,
                acceptance_criteria="Done",
                status=MilestoneStatus.PASSED,
                selected_model=None,
                generated_prompt=None,
                worker_output=None,
                qa_feedback=None,
                retry_count=0,
            ),
            MilestoneData(
                id=uuid4(),
                description="Task 2",
                complexity=TaskComplexity.SIMPLE,
                acceptance_criteria="Done",
                status=MilestoneStatus.PENDING,
                selected_model=None,
                generated_prompt=None,
                worker_output=None,
                qa_feedback=None,
                retry_count=0,
            ),
        ]

        state: AgentState = {
            "task_id": uuid4(),
            "milestones": milestones,
            "current_milestone_index": 0,
            "current_qa_decision": "pass",
        }

        result = await advance_node(state, mock_session)

        assert result["current_milestone_index"] == 1
        assert result["retry_count"] == 0
        assert result["should_continue"] is True

    @pytest.mark.asyncio
    async def test_pass_completes_workflow(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test workflow completion when last milestone passes."""
        milestone = MilestoneData(
            id=uuid4(),
            description="Task",
            complexity=TaskComplexity.SIMPLE,
            acceptance_criteria="Done",
            status=MilestoneStatus.PASSED,
            selected_model=None,
            generated_prompt=None,
            worker_output=None,
            qa_feedback=None,
            retry_count=0,
        )

        state: AgentState = {
            "task_id": uuid4(),
            "milestones": [milestone],
            "current_milestone_index": 0,
            "current_qa_decision": "pass",
        }

        result = await advance_node(state, mock_session)

        assert result["task_status"] == TaskStatus.COMPLETED
        assert result["workflow_complete"] is True
