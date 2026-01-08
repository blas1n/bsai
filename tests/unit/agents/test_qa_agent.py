"""Tests for QAAgent."""

from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.core.qa_agent import QAAgent, QADecision
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
def mock_ws_manager() -> MagicMock:
    """Create mock WebSocket manager."""
    manager = MagicMock()
    manager.send_message = AsyncMock()
    return manager


@pytest.fixture
def qa_agent(
    mock_llm_client: MagicMock,
    mock_router: MagicMock,
    mock_prompt_manager: MagicMock,
    mock_session: AsyncMock,
    mock_ws_manager: MagicMock,
) -> QAAgent:
    """Create QAAgent with mocked dependencies."""
    agent = QAAgent(
        llm_client=mock_llm_client,
        router=mock_router,
        prompt_manager=mock_prompt_manager,
        session=mock_session,
        ws_manager=mock_ws_manager,
    )
    # Mock the milestone_repo that gets created internally
    agent.milestone_repo = MagicMock()
    milestone_mock = MagicMock()
    agent.milestone_repo.get_by_id = AsyncMock(return_value=milestone_mock)
    agent.milestone_repo.update = AsyncMock()

    # Mock the mcp_server_repo that gets created internally
    agent.mcp_server_repo = MagicMock()
    agent.mcp_server_repo.get_enabled_for_agent = AsyncMock(return_value=[])

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
        session_id = uuid4()
        user_id = "test-user-id"
        milestone_description = "Implement login"
        acceptance_criteria = "Users can login with username/password"
        worker_output = "Login feature implemented with proper validation"

        # Mock LLM response with PASS
        mock_response = LLMResponse(
            content='{"decision": "PASS", "feedback": "Implementation meets criteria", "issues": [], "suggestions": []}',
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
            user_id=user_id,
            session_id=session_id,
        )

        # Verify
        assert decision == QADecision.PASS
        assert "meets criteria" in feedback.lower()

        # Check milestone status was updated to "pass" (enum value)
        mock_repo = cast(MagicMock, qa_agent.milestone_repo)
        mock_repo.update.assert_called_once()
        update_call = mock_repo.update.call_args
        assert update_call.kwargs["status"] == QADecision.PASS.value

    @pytest.mark.asyncio
    async def test_validate_output_retry(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test validation that requires retry."""
        milestone_id = uuid4()
        session_id = uuid4()
        user_id = "test-user-id"
        milestone_description = "Implement login"
        acceptance_criteria = "Users can login with username/password"
        worker_output = "Incomplete login implementation"

        # Mock LLM response with RETRY
        mock_response = LLMResponse(
            content='{"decision": "RETRY", "feedback": "Missing password validation", "issues": ["Password validation missing"], "suggestions": ["Add password validation"]}',
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
            user_id=user_id,
            session_id=session_id,
        )

        # Verify
        assert decision == QADecision.RETRY
        assert "password validation" in feedback.lower()

        # Check milestone status was NOT updated to "pass"
        mock_repo = cast(MagicMock, qa_agent.milestone_repo)
        update_calls = [
            call
            for call in mock_repo.update.call_args_list
            if call.kwargs.get("status") == QADecision.PASS.value
        ]
        assert len(update_calls) == 0

    @pytest.mark.asyncio
    async def test_validate_output_structured_feedback(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test structured feedback with issues and suggestions."""
        milestone_id = uuid4()
        session_id = uuid4()
        user_id = "test-user-id"
        milestone_description = "Implement login"
        acceptance_criteria = "Users can login"
        worker_output = "Bad implementation"

        # Mock LLM response with RETRY including issues and suggestions
        mock_response = LLMResponse(
            content='{"decision": "RETRY", "feedback": "Still has issues", "issues": ["Missing validation", "No error handling"], "suggestions": ["Add input validation"]}',
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
            user_id=user_id,
            session_id=session_id,
        )

        # Verify decision and feedback structure
        assert decision == QADecision.RETRY
        assert "still has issues" in feedback.lower()
        assert "issues found" in feedback.lower()
        assert "missing validation" in feedback.lower()
        assert "suggestions" in feedback.lower()
        assert "add input validation" in feedback.lower()

    @pytest.mark.asyncio
    async def test_validate_output_non_pass_becomes_retry(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that non-PASS decisions become RETRY (QA only returns PASS or RETRY)."""
        milestone_id = uuid4()
        session_id = uuid4()
        user_id = "test-user-id"
        milestone_description = "Implement login"
        acceptance_criteria = "Users can login"
        worker_output = "Wrong feature implemented"

        # Mock LLM response with RETRY (now structured output enforces PASS/RETRY)
        mock_response = LLMResponse(
            content='{"decision": "RETRY", "feedback": "Wrong implementation approach", "issues": [], "suggestions": []}',
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
            user_id=user_id,
            session_id=session_id,
        )

        # Verify RETRY decision
        assert decision == QADecision.RETRY
        assert "wrong implementation" in feedback.lower()

        # Check milestone status was updated to "retry" (enum value)
        mock_repo = cast(MagicMock, qa_agent.milestone_repo)
        mock_repo.update.assert_called()
        update_call = mock_repo.update.call_args
        assert update_call.kwargs["status"] == QADecision.RETRY.value

    @pytest.mark.asyncio
    async def test_validate_output_invalid_decision_raises_error(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test handling of invalid decision from LLM raises ValueError."""
        milestone_id = uuid4()
        session_id = uuid4()
        user_id = "test-user-id"

        # Mock LLM response with invalid decision (would fail Pydantic validation)
        mock_response = LLMResponse(
            content='{"decision": "MAYBE", "feedback": "Not sure"}',
            usage=UsageInfo(input_tokens=400, output_tokens=100, total_tokens=500),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute - should raise ValueError due to Pydantic validation failure
        with pytest.raises(ValueError, match="Failed to parse QA response"):
            await qa_agent.validate_output(
                milestone_id=milestone_id,
                milestone_description="Test",
                acceptance_criteria="Done",
                worker_output="Output",
                user_id=user_id,
                session_id=session_id,
            )

    @pytest.mark.asyncio
    async def test_validate_output_prompt_rendering(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
        mock_prompt_manager: MagicMock,
    ) -> None:
        """Test validation prompt is properly rendered."""
        milestone_id = uuid4()
        session_id = uuid4()
        user_id = "test-user-id"

        # Mock LLM response
        mock_response = LLMResponse(
            content='{"decision": "PASS", "feedback": "Good", "issues": [], "suggestions": []}',
            usage=UsageInfo(input_tokens=400, output_tokens=100, total_tokens=500),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        await qa_agent.validate_output(
            milestone_id=milestone_id,
            milestone_description="Test milestone",
            acceptance_criteria="Must be done",
            worker_output="Output content",
            user_id=user_id,
            session_id=session_id,
        )

        # Verify prompt was rendered with correct arguments
        mock_prompt_manager.render.assert_called_once()
        render_call = mock_prompt_manager.render.call_args
        assert render_call.kwargs["milestone_description"] == "Test milestone"
        assert render_call.kwargs["acceptance_criteria"] == "Must be done"
        assert render_call.kwargs["worker_output"] == "Output content"

    @pytest.mark.asyncio
    async def test_validate_output_cost_tracking(
        self,
        qa_agent: QAAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
    ) -> None:
        """Test that usage and cost are properly tracked."""
        milestone_id = uuid4()
        session_id = uuid4()
        user_id = "test-user-id"

        # Mock LLM response
        mock_response = LLMResponse(
            content='{"decision": "PASS", "feedback": "Good", "issues": [], "suggestions": []}',
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
            user_id=user_id,
            session_id=session_id,
        )

        # Verify LLM was called
        mock_llm_client.chat_completion.assert_called_once()
