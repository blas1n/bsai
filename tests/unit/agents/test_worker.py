"""Tests for WorkerAgent."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.core.worker import WorkerAgent
from agent.db.models.enums import TaskComplexity
from agent.llm import LLMModel, LLMResponse, UsageInfo


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create mock LLM client."""
    client = MagicMock()
    client.chat_completion = AsyncMock()
    return client


@pytest.fixture
def mock_router() -> MagicMock:
    """Create mock LLM router."""
    router = MagicMock()
    router.select_model.return_value = LLMModel(
        name="gpt-4o",
        provider="openai",
        input_price_per_1k=Decimal("0.0025"),
        output_price_per_1k=Decimal("0.01"),
        context_window=128000,
        supports_streaming=True,
    )
    router.calculate_cost.return_value = Decimal("0.005")
    return router


@pytest.fixture
def mock_prompt_manager() -> MagicMock:
    """Create mock PromptManager."""
    manager = MagicMock()
    manager.render.return_value = "Retry prompt"
    return manager


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def worker(
    mock_llm_client: MagicMock,
    mock_router: MagicMock,
    mock_prompt_manager: MagicMock,
    mock_session: AsyncMock,
) -> WorkerAgent:
    """Create WorkerAgent with mocked dependencies."""
    agent = WorkerAgent(
        llm_client=mock_llm_client,
        router=mock_router,
        session=mock_session,
        prompt_manager=mock_prompt_manager,
    )
    # Mock the usage_logger and milestone_repo that get created internally

    # Mock milestone_repo
    agent.milestone_repo = MagicMock()
    mock_milestone = MagicMock()
    agent.milestone_repo.get_by_id = AsyncMock(return_value=mock_milestone)
    agent.milestone_repo.update = AsyncMock()
    return agent


class TestWorkerAgent:
    """Test WorkerAgent functionality."""

    @pytest.mark.asyncio
    async def test_execute_milestone_success(
        self,
        worker: WorkerAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test successful milestone execution."""
        milestone_id = uuid4()
        prompt = "Implement feature X"
        complexity = TaskComplexity.MODERATE

        # Mock LLM response
        mock_response = LLMResponse(
            content="Implementation completed",
            usage=UsageInfo(input_tokens=500, output_tokens=300, total_tokens=800),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        result = await worker.execute_milestone(
            milestone_id=milestone_id,
            prompt=prompt,
            complexity=complexity,
        )

        # Verify
        assert result.content == "Implementation completed"

        mock_router.select_model.assert_called_once_with(
            complexity=complexity, preferred_model=None
        )
        mock_llm_client.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_milestone_with_preferred_model(
        self,
        worker: WorkerAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test execution with user-preferred model."""
        milestone_id = uuid4()
        prompt = "Implement feature X"
        complexity = TaskComplexity.MODERATE
        preferred_model = "gpt-4o-mini"

        # Mock LLM response
        mock_response = LLMResponse(
            content="Implementation completed",
            usage=UsageInfo(input_tokens=500, output_tokens=300, total_tokens=800),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        result = await worker.execute_milestone(
            milestone_id=milestone_id,
            prompt=prompt,
            complexity=complexity,
            preferred_model=preferred_model,
        )

        # Verify
        assert result.content == "Implementation completed"
        mock_router.select_model.assert_called_once_with(
            complexity=complexity, preferred_model=preferred_model
        )

    @pytest.mark.asyncio
    async def test_execute_milestone_cost_calculation(
        self,
        worker: WorkerAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test that cost is properly calculated and logged."""
        milestone_id = uuid4()
        prompt = "Implement feature X"
        complexity = TaskComplexity.COMPLEX

        # Mock LLM response
        mock_response = LLMResponse(
            content="Implementation completed",
            usage=UsageInfo(input_tokens=1000, output_tokens=500, total_tokens=1500),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        await worker.execute_milestone(
            milestone_id=milestone_id,
            prompt=prompt,
            complexity=complexity,
        )

        # Verify cost calculation
        mock_router.calculate_cost.assert_called_once()
        call_args = mock_router.calculate_cost.call_args
        assert call_args.kwargs["input_tokens"] == 1000
        assert call_args.kwargs["output_tokens"] == 500

    @pytest.mark.asyncio
    async def test_retry_with_feedback(
        self,
        worker: WorkerAgent,
        mock_llm_client: MagicMock,
        mock_prompt_manager: MagicMock,
    ) -> None:
        """Test retry execution with QA feedback."""
        milestone_id = uuid4()
        original_prompt = "Implement feature X"
        previous_output = "Incomplete implementation"
        qa_feedback = "Missing error handling"
        complexity = TaskComplexity.MODERATE

        # Mock LLM response
        mock_response = LLMResponse(
            content="Improved implementation",
            usage=UsageInfo(input_tokens=600, output_tokens=400, total_tokens=1000),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        result = await worker.retry_with_feedback(
            milestone_id=milestone_id,
            original_prompt=original_prompt,
            previous_output=previous_output,
            qa_feedback=qa_feedback,
            complexity=complexity,
        )

        # Verify
        assert result.content == "Improved implementation"

        # Check retry prompt was generated
        mock_prompt_manager.render.assert_called_once()
        render_call = mock_prompt_manager.render.call_args
        assert render_call.kwargs["previous_output"] == previous_output
        assert render_call.kwargs["qa_feedback"] == qa_feedback
        assert render_call.kwargs["original_prompt"] == original_prompt

    @pytest.mark.asyncio
    async def test_execute_milestone_all_complexities(
        self,
        worker: WorkerAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test execution with all complexity levels."""
        milestone_id = uuid4()
        prompt = "Test task"

        complexities = [
            TaskComplexity.TRIVIAL,
            TaskComplexity.SIMPLE,
            TaskComplexity.MODERATE,
            TaskComplexity.COMPLEX,
            TaskComplexity.CONTEXT_HEAVY,
        ]

        # Mock LLM response
        mock_response = LLMResponse(
            content="Task completed",
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        for complexity in complexities:
            # Execute
            result = await worker.execute_milestone(
                milestone_id=milestone_id,
                prompt=prompt,
                complexity=complexity,
            )

            # Verify
            assert result.content == "Task completed"

            # Check correct complexity was passed to router
            last_call = mock_router.select_model.call_args
            assert last_call.kwargs["complexity"] == complexity

    @pytest.mark.asyncio
    async def test_execute_milestone_empty_output(
        self,
        worker: WorkerAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test handling of empty LLM output."""
        milestone_id = uuid4()
        prompt = "Test task"
        complexity = TaskComplexity.SIMPLE

        # Mock empty LLM response
        mock_response = LLMResponse(
            content="",
            usage=UsageInfo(input_tokens=100, output_tokens=0, total_tokens=100),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        result = await worker.execute_milestone(
            milestone_id=milestone_id,
            prompt=prompt,
            complexity=complexity,
        )

        # Should return empty string without error
        assert result.content == ""
