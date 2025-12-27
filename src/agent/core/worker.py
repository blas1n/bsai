"""Worker Agent for task execution.

The Worker is responsible for:
1. Executing actual tasks based on prompts
2. Using dynamically selected LLM based on complexity
3. Generating output based on acceptance criteria
4. Tracking execution metadata
"""

from collections.abc import AsyncIterator
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.container import get_container
from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMResponse, LLMRouter
from agent.prompts import WorkerPrompts

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
        session: AsyncSession,
    ) -> None:
        """Initialize Worker agent.

        Args:
            llm_client: LLM client for API calls
            router: Router for model selection
            session: Database session
        """
        self.llm_client = llm_client
        self.router = router
        self.session = session
        self.milestone_repo = MilestoneRepository(session)
        self.prompt_manager = get_container().prompt_manager

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
                status=MilestoneStatus.IN_PROGRESS,
            )

        # Select model based on complexity
        model = self.router.select_model(
            complexity=complexity,
            preferred_model=preferred_model,
        )

        # Build messages list
        messages = context_messages or []
        messages.append(ChatMessage(role="user", content=prompt))

        # Execute task
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=0.7,  # Standard temperature for balanced creativity
            api_base=model.api_base,
            api_key=model.api_key,
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

    async def execute_with_streaming(
        self,
        milestone_id: UUID,
        prompt: str,
        complexity: TaskComplexity,
        preferred_model: str | None = None,
        context_messages: list[ChatMessage] | None = None,
    ) -> AsyncIterator[str]:
        """Execute milestone with streaming response.

        Args:
            milestone_id: Milestone ID being executed
            prompt: Execution prompt
            complexity: Milestone complexity level
            preferred_model: Optional user-preferred model override
            context_messages: Optional conversation history

        Yields:
            Text chunks from streaming response

        Raises:
            ValueError: If model selection fails or model doesn't support streaming
        """
        logger.info(
            "worker_streaming_start",
            milestone_id=str(milestone_id),
            complexity=complexity.name,
        )

        # Update milestone status
        milestone = await self.milestone_repo.get_by_id(milestone_id)
        if milestone:
            await self.milestone_repo.update(
                milestone_id,
                status=MilestoneStatus.IN_PROGRESS,
            )

        # Select model
        model = self.router.select_model(
            complexity=complexity,
            preferred_model=preferred_model,
        )

        if not model.supports_streaming:
            raise ValueError(
                f"Model '{model.name}' does not support streaming. "
                "Use execute_milestone() instead."
            )

        # Build messages
        messages = context_messages or []
        messages.append(ChatMessage(role="user", content=prompt))

        # Stream execution
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=0.7,
            stream=True,
            api_base=model.api_base,
            api_key=model.api_key,
        )

        chunk_count = 0
        async for chunk in self.llm_client.stream_completion(request):
            chunk_count += 1
            yield chunk

        logger.info(
            "worker_streaming_complete",
            milestone_id=str(milestone_id),
            model=model.name,
            chunks=chunk_count,
        )

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
