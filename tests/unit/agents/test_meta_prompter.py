"""Tests for MetaPrompterAgent."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.core.meta_prompter import MetaPrompterAgent
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
        name="claude-3-5-sonnet-20241022",
        provider="anthropic",
        input_price_per_1k=Decimal("0.003"),
        output_price_per_1k=Decimal("0.015"),
        context_window=200000,
        supports_streaming=True,
    )
    router.calculate_cost.return_value = Decimal("0.002")
    return router


@pytest.fixture
def mock_prompt_manager() -> MagicMock:
    """Create mock PromptManager."""
    manager = MagicMock()
    manager.render.return_value = "Optimized prompt"
    manager.get_data.return_value = {
        "TRIVIAL": "Use simple instructions",
        "SIMPLE": "Use clear step-by-step instructions",
        "MODERATE": "Use structured approach",
        "COMPLEX": "Use detailed reasoning",
        "CONTEXT_HEAVY": "Use comprehensive context",
    }
    return manager


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def meta_prompter(
    mock_llm_client: MagicMock,
    mock_router: MagicMock,
    mock_prompt_manager: MagicMock,
    mock_session: AsyncMock,
) -> MetaPrompterAgent:
    """Create MetaPrompterAgent with mocked dependencies."""
    agent = MetaPrompterAgent(
        llm_client=mock_llm_client,
        router=mock_router,
        prompt_manager=mock_prompt_manager,
        session=mock_session,
    )
    # Mock the prompt_repo that gets created internally
    agent.prompt_repo = MagicMock()
    agent.prompt_repo.create = AsyncMock()
    return agent


class TestMetaPrompterAgent:
    """Test MetaPrompterAgent functionality."""

    @pytest.mark.asyncio
    async def test_generate_prompt_simple(
        self,
        meta_prompter: MetaPrompterAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
        mock_prompt_manager: MagicMock,
    ) -> None:
        """Test generating optimized prompt for simple task."""
        milestone_id = uuid4()
        milestone_description = "Setup project structure"
        complexity = TaskComplexity.SIMPLE
        acceptance_criteria = "Project initialized"

        # Mock LLM response
        mock_response = LLMResponse(
            content="Optimized prompt for worker",
            usage=UsageInfo(input_tokens=200, output_tokens=100, total_tokens=300),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        result = await meta_prompter.generate_prompt(
            milestone_id=milestone_id,
            milestone_description=milestone_description,
            milestone_complexity=complexity,
            acceptance_criteria=acceptance_criteria,
        )

        # Verify
        assert result == "Optimized prompt for worker"

        mock_router.select_model.assert_called_once_with(TaskComplexity.MODERATE)
        mock_prompt_manager.get_data.assert_called_once()
        mock_prompt_manager.render.assert_called_once()
        mock_llm_client.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_prompt_with_context(
        self,
        meta_prompter: MetaPrompterAgent,
        mock_llm_client: MagicMock,
        mock_prompt_manager: MagicMock,
    ) -> None:
        """Test generating prompt with additional context."""
        milestone_id = uuid4()
        milestone_description = "Implement authentication"
        complexity = TaskComplexity.COMPLEX
        acceptance_criteria = "Users can login"
        context = "Use JWT tokens for authentication"

        # Mock LLM response
        mock_response = LLMResponse(
            content="Optimized prompt with context",
            usage=UsageInfo(input_tokens=300, output_tokens=150, total_tokens=450),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        result = await meta_prompter.generate_prompt(
            milestone_id=milestone_id,
            milestone_description=milestone_description,
            milestone_complexity=complexity,
            acceptance_criteria=acceptance_criteria,
            context=context,
        )

        # Verify
        assert result == "Optimized prompt with context"

        # Check that context was passed to render as additional_context
        render_call = mock_prompt_manager.render.call_args
        assert render_call.kwargs["additional_context"] == context

    @pytest.mark.asyncio
    async def test_generate_prompt_all_complexities(
        self,
        meta_prompter: MetaPrompterAgent,
        mock_llm_client: MagicMock,
        mock_prompt_manager: MagicMock,
    ) -> None:
        """Test prompt generation for all complexity levels."""
        milestone_id = uuid4()

        complexities = [
            TaskComplexity.TRIVIAL,
            TaskComplexity.SIMPLE,
            TaskComplexity.MODERATE,
            TaskComplexity.COMPLEX,
            TaskComplexity.CONTEXT_HEAVY,
        ]

        # Mock LLM response
        mock_response = LLMResponse(
            content="Optimized prompt",
            usage=UsageInfo(input_tokens=200, output_tokens=100, total_tokens=300),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        for complexity in complexities:
            # Execute
            result = await meta_prompter.generate_prompt(
                milestone_id=milestone_id,
                milestone_description=f"Test {complexity.name}",
                milestone_complexity=complexity,
                acceptance_criteria="Done",
            )

            # Verify
            assert result == "Optimized prompt"

            # Check that correct complexity was used
            render_call = mock_prompt_manager.render.call_args
            assert render_call.kwargs["complexity"] == complexity.name

    @pytest.mark.asyncio
    async def test_generate_prompt_strategy_selection(
        self,
        meta_prompter: MetaPrompterAgent,
        mock_llm_client: MagicMock,
        mock_prompt_manager: MagicMock,
    ) -> None:
        """Test that correct strategy is selected based on complexity."""
        milestone_id = uuid4()

        # Mock LLM response
        mock_response = LLMResponse(
            content="Optimized prompt",
            usage=UsageInfo(input_tokens=200, output_tokens=100, total_tokens=300),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Test COMPLEX complexity gets COMPLEX strategy
        await meta_prompter.generate_prompt(
            milestone_id=milestone_id,
            milestone_description="Complex task",
            milestone_complexity=TaskComplexity.COMPLEX,
            acceptance_criteria="Done",
        )

        render_call = mock_prompt_manager.render.call_args
        assert "Use detailed reasoning" in render_call.kwargs["strategy"]

    @pytest.mark.asyncio
    async def test_generate_prompt_cost_logging(
        self,
        meta_prompter: MetaPrompterAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test that usage and cost are properly logged."""
        milestone_id = uuid4()

        # Mock LLM response
        mock_response = LLMResponse(
            content="Optimized prompt",
            usage=UsageInfo(input_tokens=200, output_tokens=100, total_tokens=300),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        await meta_prompter.generate_prompt(
            milestone_id=milestone_id,
            milestone_description="Test",
            milestone_complexity=TaskComplexity.MODERATE,
            acceptance_criteria="Done",
        )

        # Verify LLM was called
        mock_llm_client.chat_completion.assert_called_once()
