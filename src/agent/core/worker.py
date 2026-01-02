"""Worker Agent for task execution.

The Worker is responsible for:
1. Executing actual tasks based on prompts
2. Using dynamically selected LLM based on complexity
3. Generating output based on acceptance criteria
4. Tracking execution metadata
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMResponse, LLMRouter
from agent.llm.schemas import WorkerOutput
from agent.prompts import PromptManager, WorkerPrompts

logger = structlog.get_logger()


class WorkerAgent:
    """Worker agent for executing milestones.

    Uses dynamically selected LLM based on milestone complexity,
    optimizing for both cost and quality.
    """

    def __init__(
        self,
        llm_client: LiteLLMClient,
        router: LLMRouter,
        prompt_manager: PromptManager,
        session: AsyncSession,
    ) -> None:
        """Initialize Worker agent.

        Args:
            llm_client: LLM client for API calls
            router: Router for model selection
            prompt_manager: Prompt manager for template rendering
            session: Database session
        """
        self.llm_client = llm_client
        self.router = router
        self.prompt_manager = prompt_manager
        self.session = session
        self.milestone_repo = MilestoneRepository(session)

    async def execute_milestone(
        self,
        milestone_id: UUID,
        prompt: str,
        complexity: TaskComplexity,
        preferred_model: str | None = None,
        context_messages: list[ChatMessage] | None = None,
    ) -> LLMResponse:
        """Execute a milestone using the provided prompt.

        Args:
            milestone_id: Milestone ID being executed
            prompt: Execution prompt (from Meta Prompter or direct)
            complexity: Milestone complexity level
            preferred_model: Optional user-preferred model override
            context_messages: Optional conversation history for context

        Returns:
            LLM response with execution result

        Raises:
            ValueError: If model selection fails
        """
        logger.info(
            "worker_execution_start",
            milestone_id=str(milestone_id),
            complexity=complexity.name,
            prompt_length=len(prompt),
        )

        # Update milestone status to in_progress
        milestone = await self.milestone_repo.get_by_id(milestone_id)
        if milestone:
            await self.milestone_repo.update(
                milestone_id,
                status=MilestoneStatus.IN_PROGRESS.value,
            )

        # Select model based on complexity
        model = self.router.select_model(
            complexity=complexity,
            preferred_model=preferred_model,
        )

        # Get system prompt for output format guidelines
        system_prompt = self.prompt_manager.get_data("worker", WorkerPrompts.SYSTEM_PROMPT)

        # Build messages list with system prompt
        messages = []
        messages.append(ChatMessage(role="system", content=system_prompt))
        if context_messages:
            messages.extend(context_messages)
        messages.append(ChatMessage(role="user", content=prompt))

        # Execute task with structured output
        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=settings.worker_temperature,
            api_base=model.api_base,
            api_key=model.api_key,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "worker_output",
                    "strict": True,
                    "schema": WorkerOutput.model_json_schema(),
                },
            },
        )

        response = await self.llm_client.chat_completion(request)

        # Calculate cost
        cost = self.router.calculate_cost(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        logger.info(
            "worker_execution_complete",
            milestone_id=str(milestone_id),
            model=model.name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=float(cost),
        )

        return response

    async def retry_with_feedback(
        self,
        milestone_id: UUID,
        original_prompt: str,
        previous_output: str,
        qa_feedback: str,
        complexity: TaskComplexity,
    ) -> LLMResponse:
        """Retry milestone execution with QA feedback.

        Args:
            milestone_id: Milestone ID being retried
            original_prompt: Original execution prompt
            previous_output: Previous attempt output
            qa_feedback: Feedback from QA Agent
            complexity: Milestone complexity

        Returns:
            LLM response from retry attempt
        """
        logger.info(
            "worker_retry_start",
            milestone_id=str(milestone_id),
            feedback_length=len(qa_feedback),
        )

        # Build retry prompt with feedback
        retry_prompt = self.prompt_manager.render(
            "worker",
            WorkerPrompts.RETRY_PROMPT,
            previous_output=previous_output,
            qa_feedback=qa_feedback,
            original_prompt=original_prompt,
        )

        # Execute retry (reuse execute_milestone logic)
        response = await self.execute_milestone(
            milestone_id=milestone_id,
            prompt=retry_prompt,
            complexity=complexity,
        )

        logger.info(
            "worker_retry_complete",
            milestone_id=str(milestone_id),
        )

        return response
