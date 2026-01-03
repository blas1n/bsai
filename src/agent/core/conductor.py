"""Conductor Agent for request analysis and milestone breakdown.

The Conductor is responsible for:
1. Breaking user requests into manageable milestones
2. Analyzing complexity of each milestone
3. Selecting optimal LLM for each milestone
4. Monitoring context usage
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import TaskComplexity
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.db.repository.task_repo import TaskRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMRouter
from agent.llm.schemas import ConductorOutput
from agent.prompts import ConductorPrompts, PromptManager

logger = structlog.get_logger()


class ConductorAgent:
    """Conductor agent for task analysis and planning.

    Uses a lightweight LLM to minimize costs while providing intelligent
    task breakdown and complexity analysis.
    """

    def __init__(
        self,
        llm_client: LiteLLMClient,
        router: LLMRouter,
        prompt_manager: PromptManager,
        session: AsyncSession,
    ) -> None:
        """Initialize Conductor agent.

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
        self.task_repo = TaskRepository(session)
        self.milestone_repo = MilestoneRepository(session)

    async def analyze_and_plan(
        self,
        task_id: UUID,
        original_request: str,
    ) -> list[dict[str, str | TaskComplexity]]:
        """Analyze user request and create milestone plan.

        Args:
            task_id: Task ID to associate milestones with
            original_request: Original user request

        Returns:
            List of milestone definitions with:
                - description: What needs to be done
                - complexity: TaskComplexity enum value
                - acceptance_criteria: Success criteria

        Raises:
            ValueError: If LLM response is invalid
        """
        logger.info(
            "conductor_analysis_start",
            task_id=str(task_id),
            request_length=len(original_request),
        )

        # Use TRIVIAL complexity for Conductor (lightweight LLM)
        model = self.router.select_model(TaskComplexity.TRIVIAL)

        # Build analysis prompt
        prompt = self._build_analysis_prompt(original_request)
        messages = [ChatMessage(role="user", content=prompt)]

        # Call LLM with structured output
        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=settings.conductor_temperature,
            api_base=model.api_base,
            api_key=model.api_key,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "conductor_output",
                    "strict": True,
                    "schema": ConductorOutput.model_json_schema(),
                },
            },
        )

        response = await self.llm_client.chat_completion(request)

        # Parse structured response
        try:
            milestones = self._parse_milestones(response.content)
        except (ValueError, KeyError) as e:
            logger.error(
                "conductor_parse_failed",
                task_id=str(task_id),
                error=str(e),
                response=response.content[:500],
            )
            raise ValueError(f"Failed to parse Conductor response: {e}") from e

        # Persist milestones to database
        await self._persist_milestones(task_id, milestones)

        logger.info(
            "conductor_analysis_complete",
            task_id=str(task_id),
            milestone_count=len(milestones),
            total_tokens=response.usage.total_tokens,
        )

        return milestones

    def _build_analysis_prompt(self, original_request: str) -> str:
        """Build prompt for task analysis.

        Args:
            original_request: User's original request

        Returns:
            Formatted prompt for LLM
        """
        return self.prompt_manager.render(
            "conductor",
            ConductorPrompts.ANALYSIS_PROMPT,
            original_request=original_request,
        )

    def _parse_milestones(self, response_content: str) -> list[dict[str, str | TaskComplexity]]:
        """Parse LLM response into milestone definitions.

        Args:
            response_content: Raw LLM response (structured JSON)

        Returns:
            List of milestone dictionaries

        Raises:
            ValueError: If response validation fails
        """
        # Parse using Pydantic model
        output = ConductorOutput.model_validate_json(response_content)

        milestones = []
        for m in output.milestones:
            # Convert complexity string to enum
            try:
                complexity = TaskComplexity[m.complexity]
            except KeyError:
                logger.warning(
                    "invalid_complexity",
                    provided=m.complexity,
                    defaulting_to="MODERATE",
                )
                complexity = TaskComplexity.MODERATE

            milestones.append(
                {
                    "description": m.description,
                    "complexity": complexity,
                    "acceptance_criteria": m.acceptance_criteria,
                }
            )

        return milestones

    async def _persist_milestones(
        self,
        task_id: UUID,
        milestones: list[dict[str, str | TaskComplexity]],
    ) -> None:
        """Persist milestones to database.

        Args:
            task_id: Parent task ID
            milestones: List of milestone definitions
        """
        for sequence, milestone in enumerate(milestones, start=1):
            complexity_value = milestone["complexity"]
            assert isinstance(complexity_value, TaskComplexity)

            await self.milestone_repo.create(
                task_id=task_id,
                title=str(milestone.get("title", f"Milestone {sequence}")),
                description=str(milestone["description"]),
                complexity=complexity_value.value,
                sequence_number=sequence,
                acceptance_criteria=str(milestone["acceptance_criteria"]),
            )

        logger.debug(
            "milestones_persisted",
            task_id=str(task_id),
            count=len(milestones),
        )

    async def select_model_for_milestone(
        self,
        complexity: TaskComplexity,
        preferred_model: str | None = None,
    ) -> str:
        """Select optimal LLM model for a milestone.

        Args:
            complexity: Milestone complexity level
            preferred_model: Optional user-preferred model override

        Returns:
            Selected model name

        Raises:
            ValueError: If model not found in registry
        """
        model = self.router.select_model(
            complexity=complexity,
            preferred_model=preferred_model,
        )

        logger.debug(
            "model_selected",
            complexity=complexity.name,
            model=model.name,
            provider=model.provider,
        )

        return model.name
