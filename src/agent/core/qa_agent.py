"""QA Agent for output validation and feedback.

The QA Agent is responsible for:
1. Validating Worker outputs against acceptance criteria
2. Providing structured feedback for improvements
3. Deciding whether to pass, fail, or retry
4. Tracking validation history
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import TaskComplexity
from agent.db.repository.mcp_server_repo import McpServerRepository
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMRouter
from agent.llm.schemas import QAOutput
from agent.mcp.executor import McpToolExecutor
from agent.mcp.utils import load_user_mcp_servers
from agent.prompts import PromptManager, QAAgentPrompts

if TYPE_CHECKING:
    from agent.api.websocket.manager import ConnectionManager
    from agent.db.models.mcp_server_config import McpServerConfig

logger = structlog.get_logger()


class QADecision(str, Enum):
    """QA validation decision.

    Note: FAIL is only set by the system when max retries are exceeded.
    The QA prompt only offers PASS/RETRY options to prevent premature failure.
    """

    PASS = "pass"
    RETRY = "retry"
    FAIL = "fail"  # Only set by system when max retries exceeded


class QAAgent:
    """QA agent for validating Worker outputs.

    Uses a medium-complexity LLM to provide independent validation
    and structured feedback for quality assurance.
    """

    def __init__(
        self,
        llm_client: LiteLLMClient,
        router: LLMRouter,
        prompt_manager: PromptManager,
        session: AsyncSession,
        ws_manager: ConnectionManager,
    ) -> None:
        """Initialize QA agent.

        Args:
            llm_client: LLM client for API calls
            router: Router for model selection
            prompt_manager: Prompt manager for template rendering
            session: Database session
            ws_manager: WebSocket manager
        """
        self.llm_client = llm_client
        self.router = router
        self.prompt_manager = prompt_manager
        self.session = session
        self.milestone_repo = MilestoneRepository(session)
        self.mcp_server_repo = McpServerRepository(session)
        self.ws_manager = ws_manager

    async def validate_output(
        self,
        milestone_id: UUID,
        milestone_description: str,
        acceptance_criteria: str,
        worker_output: str,
        user_id: str,
        session_id: UUID,
        mcp_enabled: bool = True,
    ) -> tuple[QADecision, str]:
        """Validate Worker output against acceptance criteria.

        Args:
            milestone_id: Milestone ID being validated
            milestone_description: Original milestone description
            acceptance_criteria: Success criteria
            worker_output: Output from Worker agent
            user_id: User ID for MCP tool ownership
            session_id: Session ID for MCP tool logging
            mcp_enabled: Enable MCP tool calling (default: True)

        Returns:
            Tuple of (decision, feedback):
                - decision: PASS or RETRY
                - feedback: Structured feedback for Worker

        Raises:
            ValueError: If LLM response is invalid
        """
        logger.info(
            "qa_validation_start",
            milestone_id=str(milestone_id),
            output_length=len(worker_output),
            mcp_enabled=mcp_enabled,
        )

        # Use MODERATE complexity for QA (medium LLM)
        model = self.router.select_model(TaskComplexity.MODERATE)

        # Build validation prompt
        validation_prompt = self._build_validation_prompt(
            milestone_description,
            acceptance_criteria,
            worker_output,
        )

        messages = [ChatMessage(role="user", content=validation_prompt)]

        # Call LLM with structured output
        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=settings.qa_temperature,
            api_base=model.api_base,
            api_key=model.api_key,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "qa_output",
                    "strict": True,
                    "schema": QAOutput.model_json_schema(),
                },
            },
        )

        # Load MCP servers if enabled
        mcp_servers: list[McpServerConfig] = []
        tool_executor: McpToolExecutor | None = None

        if mcp_enabled:
            mcp_servers = await load_user_mcp_servers(
                mcp_server_repo=self.mcp_server_repo,
                user_id=user_id,
                agent_type="qa",
            )

            if mcp_servers:
                tool_executor = McpToolExecutor(
                    user_id=user_id,
                    session_id=session_id,
                    ws_manager=self.ws_manager,
                )
                logger.info(
                    "qa_mcp_enabled",
                    milestone_id=str(milestone_id),
                    mcp_server_count=len(mcp_servers),
                )

        # Execute with or without tools (unified interface)
        response = await self.llm_client.chat_completion(
            request=request,
            mcp_servers=mcp_servers if tool_executor else None,
            tool_executor=tool_executor,
        )

        # Parse structured response
        try:
            decision, feedback = self._parse_validation_response(response.content)
        except (ValueError, KeyError) as e:
            logger.error(
                "qa_parse_failed",
                milestone_id=str(milestone_id),
                error=str(e),
                response=response.content[:500],
            )
            raise ValueError(f"Failed to parse QA response: {e}") from e

        # Update milestone status based on decision
        await self._update_milestone_status(milestone_id, decision)

        logger.info(
            "qa_validation_complete",
            milestone_id=str(milestone_id),
            decision=decision.value,
            tokens=response.usage.total_tokens,
        )

        return decision, feedback

    def _build_validation_prompt(
        self,
        milestone_description: str,
        acceptance_criteria: str,
        worker_output: str,
    ) -> str:
        """Build validation prompt for QA.

        Args:
            milestone_description: Original milestone description
            acceptance_criteria: Success criteria
            worker_output: Output to validate

        Returns:
            Formatted validation prompt
        """
        return self.prompt_manager.render(
            "qa_agent",
            QAAgentPrompts.VALIDATION_PROMPT,
            milestone_description=milestone_description,
            acceptance_criteria=acceptance_criteria,
            worker_output=worker_output,
        )

    def _parse_validation_response(
        self,
        response_content: str,
    ) -> tuple[QADecision, str]:
        """Parse QA validation response.

        Args:
            response_content: Raw LLM response (structured JSON)

        Returns:
            Tuple of (decision, formatted_feedback)

        Raises:
            ValueError: If response validation fails
        """
        # Parse using Pydantic model
        output = QAOutput.model_validate_json(response_content)

        # Map decision string to enum
        if output.decision == "PASS":
            decision = QADecision.PASS
        else:
            decision = QADecision.RETRY

        # Format feedback
        feedback_parts = [output.feedback]

        if decision == QADecision.RETRY and output.issues:
            feedback_parts.append("\n\nISSUES FOUND:")
            for issue in output.issues:
                feedback_parts.append(f"- {issue}")

        if decision == QADecision.RETRY and output.suggestions:
            feedback_parts.append("\n\nSUGGESTIONS:")
            for suggestion in output.suggestions:
                feedback_parts.append(f"- {suggestion}")

        formatted_feedback = "\n".join(feedback_parts)

        return decision, formatted_feedback

    async def _update_milestone_status(
        self,
        milestone_id: UUID,
        decision: QADecision,
    ) -> None:
        """Update milestone status based on QA decision.

        Args:
            milestone_id: Milestone ID
            decision: QA decision
        """
        milestone = await self.milestone_repo.get_by_id(milestone_id)
        if not milestone:
            return

        await self.milestone_repo.update(
            milestone_id,
            status=decision.value,
        )

        logger.debug(
            "milestone_status_updated",
            milestone_id=str(milestone_id),
            status=decision.value,
        )
