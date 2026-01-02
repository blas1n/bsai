"""Tests for ConductorAgent."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.core.conductor import ConductorAgent
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
        name="gpt-4o-mini",
        provider="openai",
        input_price_per_1k=Decimal("0.00015"),
        output_price_per_1k=Decimal("0.0006"),
        context_window=128000,
        supports_streaming=True,
    )
    router.calculate_cost.return_value = Decimal("0.001")
    return router


@pytest.fixture
def mock_prompt_manager() -> MagicMock:
    """Create mock PromptManager."""
    manager = MagicMock()
    manager.render.return_value = "Mocked prompt"
    return manager


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def conductor(
    mock_llm_client: MagicMock,
    mock_router: MagicMock,
    mock_prompt_manager: MagicMock,
    mock_session: AsyncMock,
) -> ConductorAgent:
    """Create ConductorAgent with mocked dependencies."""
    agent = ConductorAgent(
        llm_client=mock_llm_client,
        router=mock_router,
        prompt_manager=mock_prompt_manager,
        session=mock_session,
    )
    # Mock the milestone_repo that gets created internally
    agent.milestone_repo = MagicMock()
    agent.milestone_repo.create = AsyncMock()
    return agent


class TestConductorAgent:
    """Test ConductorAgent functionality."""

    @pytest.mark.asyncio
    async def test_analyze_and_plan_success(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
        mock_prompt_manager: MagicMock,
    ) -> None:
        """Test successful task analysis and planning."""
        task_id = uuid4()
        original_request = "Build a web scraper"

        # Mock LLM response with valid JSON
        mock_response = LLMResponse(
            content='{"milestones": [{"description": "Initialize repo", "complexity": "SIMPLE", "acceptance_criteria": "Repo created"}]}',
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        milestones = await conductor.analyze_and_plan(task_id, original_request)

        # Verify
        assert len(milestones) == 1
        assert milestones[0]["description"] == "Initialize repo"
        assert milestones[0]["complexity"] == TaskComplexity.SIMPLE
        assert milestones[0]["acceptance_criteria"] == "Repo created"

        mock_router.select_model.assert_called_once_with(TaskComplexity.TRIVIAL)
        mock_prompt_manager.render.assert_called_once()
        mock_llm_client.chat_completion.assert_called_once()
        conductor.milestone_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_and_plan_invalid_json(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test error handling for invalid JSON response."""
        task_id = uuid4()
        original_request = "Build a web scraper"

        # Mock LLM response with invalid JSON
        mock_response = LLMResponse(
            content="Invalid JSON response",
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Should raise ValueError
        with pytest.raises(ValueError, match="Failed to parse Conductor response"):
            await conductor.analyze_and_plan(task_id, original_request)

    @pytest.mark.asyncio
    async def test_analyze_and_plan_missing_milestones_key(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test error handling when milestones key is missing."""
        task_id = uuid4()
        original_request = "Build a web scraper"

        # Mock LLM response with valid JSON but missing milestones
        mock_response = LLMResponse(
            content='{"error": "no milestones"}',
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Should raise ValueError
        with pytest.raises(ValueError, match="Failed to parse Conductor response"):
            await conductor.analyze_and_plan(task_id, original_request)

    @pytest.mark.asyncio
    async def test_analyze_and_plan_complexity_validation(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test complexity validation - invalid complexity raises error."""
        task_id = uuid4()
        original_request = "Build a web scraper"

        # Mock LLM response with invalid complexity
        # With structured output, Pydantic will reject invalid complexity values
        mock_response = LLMResponse(
            content='{"milestones": [{"description": "Test", "complexity": "INVALID", "acceptance_criteria": "Done"}]}',
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Should raise ValueError due to Pydantic validation failure
        with pytest.raises(ValueError, match="Failed to parse Conductor response"):
            await conductor.analyze_and_plan(task_id, original_request)

    @pytest.mark.asyncio
    async def test_analyze_and_plan_multiple_milestones(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test handling multiple milestones."""
        task_id = uuid4()
        original_request = "Build a web scraper"

        # Mock LLM response with multiple milestones
        mock_response = LLMResponse(
            content='{"milestones": [{"description": "D1", "complexity": "SIMPLE", "acceptance_criteria": "AC1"}, {"description": "D2", "complexity": "COMPLEX", "acceptance_criteria": "AC2"}]}',
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        milestones = await conductor.analyze_and_plan(task_id, original_request)

        # Verify
        assert len(milestones) == 2
        assert milestones[0]["complexity"] == TaskComplexity.SIMPLE
        assert milestones[1]["complexity"] == TaskComplexity.COMPLEX

        # Should create both milestones in DB
        assert conductor.milestone_repo.create.call_count == 2
