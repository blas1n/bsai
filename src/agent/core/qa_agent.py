"""QA Agent for output validation and feedback.

The QA Agent is responsible for:
1. Validating Worker outputs against acceptance criteria
2. Providing structured feedback for improvements
3. Deciding whether to pass, fail, or retry
4. Tracking validation history
"""

import json
from enum import Enum
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMRouter
from agent.prompts import PromptManager, QAAgentPrompts

logger = structlog.get_logger()


class QADecision(str, Enum):
    """QA validation decision."""

    PASS = "pass"
    RETRY = "retry"
    FAIL = "fail"


class QAAgent:
    """QA agent for validating Worker outputs.

    Uses a medium-complexity LLM to provide independent validation
    and structured feedback for quality assurance.
    """

    def __init__(
        self,
        llm_client: LiteLLMClient,
        router: LLMRouter,
        session: AsyncSession,
        max_retries: int = 3,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        """Initialize QA agent.

        Args:
            llm_client: LLM client for API calls
            router: Router for model selection
            session: Database session
            max_retries: Maximum retry attempts allowed
            prompt_manager: Optional prompt manager (defaults to new instance)
        """
        self.llm_client = llm_client
        self.router = router
        self.session = session
        self.max_retries = max_retries
        self.milestone_repo = MilestoneRepository(session)
        self.prompt_manager = prompt_manager or PromptManager()

    async def validate_output(
        self,
        milestone_id: UUID,
        milestone_description: str,
        acceptance_criteria: str,
        worker_output: str,
        attempt_number: int = 1,
    ) -> tuple[QADecision, str]:
        """Validate Worker output against acceptance criteria.

        Args:
            milestone_id: Milestone ID being validated
            milestone_description: Original milestone description
            acceptance_criteria: Success criteria
            worker_output: Output from Worker agent
            attempt_number: Current attempt number (for retry limit)

        Returns:
            Tuple of (decision, feedback):
                - decision: PASS, RETRY, or FAIL
                - feedback: Structured feedback for Worker

        Raises:
            ValueError: If LLM response is invalid
        """
        logger.info(
            "qa_validation_start",
            milestone_id=str(milestone_id),
            attempt=attempt_number,
            output_length=len(worker_output),
        )

        # Use MODERATE complexity for QA (medium LLM)
        model = self.router.select_model(TaskComplexity.MODERATE)

        # Build validation prompt
        validation_prompt = self._build_validation_prompt(
            milestone_description,
            acceptance_criteria,
            worker_output,
            attempt_number,
        )

        messages = [ChatMessage(role="user", content=validation_prompt)]

        # Call LLM
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=0.2,  # Low temperature for consistent validation
            api_base=model.api_base,
            api_key=model.api_key,
        )

        response = await self.llm_client.chat_completion(request)

        # Parse response
        try:
            decision, feedback = self._parse_validation_response(
                response.content,
                attempt_number,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
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
        attempt_number: int,
    ) -> str:
        """Build validation prompt for QA.

        Args:
            milestone_description: Original milestone description
            acceptance_criteria: Success criteria
            worker_output: Output to validate
            attempt_number: Current attempt number

        Returns:
            Formatted validation prompt
        """
        # Build retry context if needed
        retry_context = ""
        if attempt_number > 1:
            retry_context_template = self.prompt_manager.get_data(
                "qa_agent", QAAgentPrompts.RETRY_CONTEXT_TEMPLATE
            )
            retry_context = self.prompt_manager.render_template(
                retry_context_template,
                cache_key="qa_agent:retry_context",
                attempt_number=attempt_number,
                max_retries=self.max_retries,
            )

        return self.prompt_manager.render(
            "qa_agent",
            QAAgentPrompts.VALIDATION_PROMPT,
            milestone_description=milestone_description,
            acceptance_criteria=acceptance_criteria,
            worker_output=worker_output,
            retry_context=retry_context,
            max_retries=self.max_retries,
        )

    def _parse_validation_response(
        self,
        response_content: str,
        attempt_number: int,
    ) -> tuple[QADecision, str]:
        """Parse QA validation response.

        Args:
            response_content: Raw LLM response
            attempt_number: Current attempt number

        Returns:
            Tuple of (decision, formatted_feedback)

        Raises:
            json.JSONDecodeError: If response is not valid JSON
            KeyError: If required fields are missing
            ValueError: If decision value is invalid
        """
        # Extract JSON from response
        content = response_content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        data = json.loads(content)

        # Parse decision
        decision_str = data["decision"].upper()
        try:
            decision = QADecision(decision_str.lower())
        except ValueError:
            # Fallback to RETRY if invalid
            logger.warning(
                "invalid_qa_decision",
                provided=decision_str,
                defaulting_to="RETRY",
            )
            decision = QADecision.RETRY

        # Check retry limit
        if decision == QADecision.RETRY and attempt_number >= self.max_retries:
            logger.warning(
                "max_retries_exceeded",
                attempt=attempt_number,
                max_retries=self.max_retries,
                changing_to="FAIL",
            )
            decision = QADecision.FAIL

        # Format feedback
        feedback_parts = [data["feedback"]]

        if decision in (QADecision.RETRY, QADecision.FAIL) and "issues" in data:
            issues = data["issues"]
            if issues:
                feedback_parts.append("\n\nISSUES FOUND:")
                for issue in issues:
                    feedback_parts.append(f"- {issue}")

        if decision == QADecision.RETRY and "suggestions" in data:
            suggestions = data["suggestions"]
            if suggestions:
                feedback_parts.append("\n\nSUGGESTIONS:")
                for suggestion in suggestions:
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

        status_map = {
            QADecision.PASS: MilestoneStatus.PASSED,
            QADecision.RETRY: MilestoneStatus.IN_PROGRESS,
            QADecision.FAIL: MilestoneStatus.FAILED,
        }

        new_status = status_map[decision]

        await self.milestone_repo.update(
            milestone_id,
            status=new_status,
        )

        logger.debug(
            "milestone_status_updated",
            milestone_id=str(milestone_id),
            status=new_status.value,
        )

    async def should_retry(
        self,
        decision: QADecision,
        attempt_number: int,
    ) -> bool:
        """Determine if Worker should retry based on QA decision.

        Args:
            decision: QA decision
            attempt_number: Current attempt number

        Returns:
            True if Worker should retry
        """
        return decision == QADecision.RETRY and attempt_number < self.max_retries
