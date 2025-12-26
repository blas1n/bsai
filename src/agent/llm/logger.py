"""LLM usage logger.

Logs LLM usage to database for cost tracking.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from agent.db.models.enums import AgentType
from agent.db.models.llm_usage_log import LLMUsageLog
from agent.db.repository.llm_usage_log_repo import LLMUsageLogRepository

from .models import LLMModel


class LLMUsageLogger:
    """Logger for tracking LLM usage in database."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize usage logger.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session
        self.repo = LLMUsageLogRepository(session)

    async def log_usage(
        self,
        session_id: UUID,
        agent_type: AgentType,
        model: LLMModel,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        cost_usd: str | float,
        milestone_id: UUID | None = None,
    ) -> LLMUsageLog:
        """Log LLM usage to database.

        Args:
            session_id: ID of the session
            agent_type: Type of agent that made the call
            model: LLM model used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            latency_ms: Request latency in milliseconds
            cost_usd: Cost in USD (will be converted to Decimal)
            milestone_id: Optional milestone ID

        Returns:
            Created LLM usage log
        """
        return await self.repo.create(
            session_id=session_id,
            milestone_id=milestone_id,
            agent_type=agent_type.value,
            llm_provider=model.provider,
            llm_model=model.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost_usd,
            latency_ms=latency_ms,
        )
