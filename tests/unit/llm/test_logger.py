"""LLM usage logger tests."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.db.models.enums import AgentType
from agent.llm.logger import LLMUsageLogger
from agent.llm.models import LLMModel

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def logger(mock_session: AsyncMock) -> LLMUsageLogger:
    """Create LLM usage logger."""
    return LLMUsageLogger(mock_session)


@pytest.fixture
def sample_model() -> LLMModel:
    """Create sample LLM model."""
    return LLMModel(
        name="gpt-4",
        provider="openai",
        input_price_per_1k=Decimal("0.03"),
        output_price_per_1k=Decimal("0.06"),
        context_window=8192,
        supports_streaming=True,
    )


class TestLogUsage:
    """Tests for log_usage method."""

    @pytest.mark.asyncio
    async def test_creates_usage_log(
        self,
        logger: LLMUsageLogger,
        sample_model: LLMModel,
    ) -> None:
        """Creates usage log in database."""
        session_id = uuid4()
        mock_log = MagicMock()

        with patch.object(logger.repo, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_log

            result = await logger.log_usage(
                session_id=session_id,
                agent_type=AgentType.ARCHITECT,
                model=sample_model,
                input_tokens=100,
                output_tokens=50,
                latency_ms=500,
                cost_usd=0.005,
            )

            assert result is mock_log
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_correct_parameters(
        self,
        logger: LLMUsageLogger,
        sample_model: LLMModel,
    ) -> None:
        """Passes correct parameters to repository."""
        session_id = uuid4()
        milestone_id = uuid4()

        with patch.object(logger.repo, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock()

            await logger.log_usage(
                session_id=session_id,
                agent_type=AgentType.WORKER,
                model=sample_model,
                input_tokens=200,
                output_tokens=100,
                latency_ms=750,
                cost_usd="0.012",
                milestone_id=milestone_id,
            )

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["session_id"] == session_id
            assert call_kwargs["milestone_id"] == milestone_id
            assert call_kwargs["agent_type"] == "worker"
            assert call_kwargs["llm_provider"] == "openai"
            assert call_kwargs["llm_model"] == "gpt-4"
            assert call_kwargs["input_tokens"] == 200
            assert call_kwargs["output_tokens"] == 100
            assert call_kwargs["latency_ms"] == 750

    @pytest.mark.asyncio
    async def test_handles_none_milestone_id(
        self,
        logger: LLMUsageLogger,
        sample_model: LLMModel,
    ) -> None:
        """Handles None milestone_id correctly."""
        session_id = uuid4()

        with patch.object(logger.repo, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock()

            await logger.log_usage(
                session_id=session_id,
                agent_type=AgentType.QA,
                model=sample_model,
                input_tokens=50,
                output_tokens=25,
                latency_ms=300,
                cost_usd=0.002,
                milestone_id=None,
            )

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["milestone_id"] is None

    @pytest.mark.asyncio
    async def test_all_agent_types(
        self,
        logger: LLMUsageLogger,
        sample_model: LLMModel,
    ) -> None:
        """Works with all agent types."""
        session_id = uuid4()

        # Simplified 4-agent workflow
        agent_types = [
            AgentType.ARCHITECT,
            AgentType.WORKER,
            AgentType.QA,
            AgentType.RESPONDER,
        ]

        for agent_type in agent_types:
            with patch.object(logger.repo, "create", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = MagicMock()

                await logger.log_usage(
                    session_id=session_id,
                    agent_type=agent_type,
                    model=sample_model,
                    input_tokens=100,
                    output_tokens=50,
                    latency_ms=500,
                    cost_usd=0.005,
                )

                call_kwargs = mock_create.call_args[1]
                assert call_kwargs["agent_type"] == agent_type.value

    @pytest.mark.asyncio
    async def test_handles_float_cost(
        self,
        logger: LLMUsageLogger,
        sample_model: LLMModel,
    ) -> None:
        """Handles float cost value."""
        session_id = uuid4()

        with patch.object(logger.repo, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock()

            await logger.log_usage(
                session_id=session_id,
                agent_type=AgentType.WORKER,
                model=sample_model,
                input_tokens=100,
                output_tokens=50,
                latency_ms=500,
                cost_usd=0.00567,
            )

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["cost"] == 0.00567

    @pytest.mark.asyncio
    async def test_handles_string_cost(
        self,
        logger: LLMUsageLogger,
        sample_model: LLMModel,
    ) -> None:
        """Handles string cost value."""
        session_id = uuid4()

        with patch.object(logger.repo, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock()

            await logger.log_usage(
                session_id=session_id,
                agent_type=AgentType.WORKER,
                model=sample_model,
                input_tokens=100,
                output_tokens=50,
                latency_ms=500,
                cost_usd="0.00567",
            )

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["cost"] == "0.00567"


class TestLLMUsageLoggerInit:
    """Tests for LLMUsageLogger initialization."""

    def test_creates_repository(self, mock_session: AsyncMock) -> None:
        """Creates repository with session."""
        with patch("agent.llm.logger.LLMUsageLogRepository") as mock_repo_class:
            logger = LLMUsageLogger(mock_session)

            mock_repo_class.assert_called_once_with(mock_session)
            assert logger.session is mock_session

    def test_stores_session(self, mock_session: AsyncMock) -> None:
        """Stores session reference."""
        logger = LLMUsageLogger(mock_session)
        assert logger.session is mock_session
