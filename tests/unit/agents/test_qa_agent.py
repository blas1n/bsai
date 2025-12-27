"""Tests for QAAgent."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.core.qa_agent import QAAgent, QADecision
from agent.db.models.enums import MilestoneStatus
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
    router.calculate_cost.return_value = Decimal("0.003")
    return router


@pytest.fixture
def mock_prompt_manager() -> MagicMock:
    """Create mock PromptManager."""
    manager = MagicMock()
    manager.render.return_value = "Validation prompt"
    manager.get_data.return_value = "Retry context template"
    manager.render_template.return_value = "Rendered retry context"
    return manager


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def qa_agent(
    mock_llm_client: MagicMock,
    mock_router: MagicMock,
    mock_prompt_manager: MagicMock,
    mock_session: AsyncMock,
) -> QAAgent:
    """Create QAAgent with mocked dependencies."""
    agent = QAAgent(
        llm_client=mock_llm_client,
        router=mock_router,
        session=mock_session,
        max_retries=3,
        prompt_manager=mock_prompt_manager,
    )
    # Mock the milestone_repo and usage_logger that get created internally
    agent.milestone_repo = MagicMock()
    milestone_mock = MagicMock()
    agent.milestone_repo.get_by_id = AsyncMock(return_value=milestone_mock)
    agent.milestone_repo.update = AsyncMock()
    return agent


class TestQAAgent:
    """Test QAAgent functionality."""

    @pytest.mark.asyncio
    async def test_validate_output_pass(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test validation that passes."""
        milestone_id = uuid4()
        milestone_description = "Implement login"
        acceptance_criteria = "Users can login with username/password"
        worker_output = "Login feature implemented with proper validation"

        # Mock LLM response with PASS
        mock_response = LLMResponse(
            content='{"decision": "PASS", "feedback": "Implementation meets criteria"}',
            usage=UsageInfo(input_tokens=400, output_tokens=100, total_tokens=500),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        decision, feedback = await qa_agent.validate_output(
            milestone_id=milestone_id,
            milestone_description=milestone_description,
            acceptance_criteria=acceptance_criteria,
            worker_output=worker_output,
        )

        # Verify
        assert decision == QADecision.PASS
        assert "meets criteria" in feedback.lower()

        # Check milestone status was updated to PASSED
        qa_agent.milestone_repo.update.assert_called_once()
        update_call = qa_agent.milestone_repo.update.call_args
        assert update_call.kwargs["status"] == MilestoneStatus.PASSED

    @pytest.mark.asyncio
    async def test_validate_output_retry(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test validation that requires retry."""
        milestone_id = uuid4()
        milestone_description = "Implement login"
        acceptance_criteria = "Users can login with username/password"
        worker_output = "Incomplete login implementation"

        # Mock LLM response with RETRY
        mock_response = LLMResponse(
            content='{"decision": "RETRY", "feedback": "Missing password validation"}',
            usage=UsageInfo(input_tokens=400, output_tokens=100, total_tokens=500),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        decision, feedback = await qa_agent.validate_output(
            milestone_id=milestone_id,
            milestone_description=milestone_description,
            acceptance_criteria=acceptance_criteria,
            worker_output=worker_output,
            attempt_number=1,
        )

        # Verify
        assert decision == QADecision.RETRY
        assert "password validation" in feedback.lower()

        # Check milestone status was NOT updated to PASSED
        update_calls = [
            call
            for call in qa_agent.milestone_repo.update.call_args_list
            if call.kwargs.get("status") == MilestoneStatus.PASSED
        ]
        assert len(update_calls) == 0

    @pytest.mark.asyncio
    async def test_validate_output_fail_max_retries(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test validation fails after max retries."""
        milestone_id = uuid4()
        milestone_description = "Implement login"
        acceptance_criteria = "Users can login"
        worker_output = "Bad implementation"

        # Mock LLM response with RETRY
        mock_response = LLMResponse(
            content='{"decision": "RETRY", "feedback": "Still has issues"}',
            usage=UsageInfo(input_tokens=400, output_tokens=100, total_tokens=500),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute with attempt_number = max_retries
        decision, feedback = await qa_agent.validate_output(
            milestone_id=milestone_id,
            milestone_description=milestone_description,
            acceptance_criteria=acceptance_criteria,
            worker_output=worker_output,
            attempt_number=3,  # max_retries
        )

        # Verify - should convert RETRY to FAIL
        assert decision == QADecision.FAIL
        assert "still has issues" in feedback.lower()

        # Check milestone status was updated to FAILED
        qa_agent.milestone_repo.update.assert_called()
        update_call = qa_agent.milestone_repo.update.call_args
        assert update_call.kwargs["status"] == MilestoneStatus.FAILED

    @pytest.mark.asyncio
    async def test_validate_output_explicit_fail(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test validation with explicit FAIL decision."""
        milestone_id = uuid4()
        milestone_description = "Implement login"
        acceptance_criteria = "Users can login"
        worker_output = "Wrong feature implemented"

        # Mock LLM response with FAIL
        mock_response = LLMResponse(
            content='{"decision": "FAIL", "feedback": "Completely wrong implementation"}',
            usage=UsageInfo(input_tokens=400, output_tokens=100, total_tokens=500),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        decision, feedback = await qa_agent.validate_output(
            milestone_id=milestone_id,
            milestone_description=milestone_description,
            acceptance_criteria=acceptance_criteria,
            worker_output=worker_output,
        )

        # Verify
        assert decision == QADecision.FAIL
        assert "wrong implementation" in feedback.lower()

        # Check milestone status was updated to FAILED
        qa_agent.milestone_repo.update.assert_called()
        update_call = qa_agent.milestone_repo.update.call_args
        assert update_call.kwargs["status"] == MilestoneStatus.FAILED

    @pytest.mark.asyncio
    async def test_validate_output_invalid_decision(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test handling of invalid decision from LLM."""
        milestone_id = uuid4()

        # Mock LLM response with invalid decision
        mock_response = LLMResponse(
            content='{"decision": "MAYBE", "feedback": "Not sure"}',
            usage=UsageInfo(input_tokens=400, output_tokens=100, total_tokens=500),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute - should default to RETRY
        decision, feedback = await qa_agent.validate_output(
            milestone_id=milestone_id,
            milestone_description="Test",
            acceptance_criteria="Done",
            worker_output="Output",
        )

        # Should fallback to RETRY for safety
        assert decision == QADecision.RETRY

    @pytest.mark.asyncio
    async def test_validate_output_retry_context_template(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
        mock_prompt_manager: MagicMock,
    ) -> None:
        """Test retry context template rendering."""
        milestone_id = uuid4()

        # Mock LLM response
        mock_response = LLMResponse(
            content='{"decision": "PASS", "feedback": "Good"}',
            usage=UsageInfo(input_tokens=400, output_tokens=100, total_tokens=500),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute with attempt > 1
        await qa_agent.validate_output(
            milestone_id=milestone_id,
            milestone_description="Test",
            acceptance_criteria="Done",
            worker_output="Output",
            attempt_number=2,
        )

        # Verify prompt was rendered
        mock_prompt_manager.render.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_output_cost_tracking(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test that usage and cost are properly tracked."""
        milestone_id = uuid4()

        # Mock LLM response
        mock_response = LLMResponse(
            content='{"decision": "PASS", "feedback": "Good"}',
            usage=UsageInfo(input_tokens=500, output_tokens=150, total_tokens=650),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        await qa_agent.validate_output(
            milestone_id=milestone_id,
            milestone_description="Test",
            acceptance_criteria="Done",
            worker_output="Output",
        )

        # Verify LLM was called
        mock_llm_client.chat_completion.assert_called_once()
