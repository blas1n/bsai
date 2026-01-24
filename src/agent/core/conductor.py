"""Conductor Agent for request analysis and milestone breakdown.

The Conductor is responsible for:
1. Breaking user requests into manageable milestones
2. Analyzing complexity of each milestone
3. Selecting optimal LLM for each milestone
4. Monitoring context usage
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import TaskComplexity
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.db.repository.task_repo import TaskRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMRouter
from agent.llm.schemas import ConductorOutput, ConductorReplanOutput
from agent.prompts import ConductorPrompts, PromptManager

if TYPE_CHECKING:
    from agent.graph.state import MilestoneData

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
        memory_context: str | None = None,
        sequence_offset: int = 0,
    ) -> list[dict[str, str | TaskComplexity]]:
        """Analyze user request and create milestone plan.

        Args:
            task_id: Task ID to associate milestones with
            original_request: Original user request
            memory_context: Optional context from long-term memory
            sequence_offset: Offset for milestone sequence numbers (for multi-task sessions)

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
            has_memory_context=bool(memory_context),
        )

        # Use TRIVIAL complexity for Conductor (lightweight LLM)
        model = self.router.select_model(TaskComplexity.TRIVIAL)

        # Build analysis prompt with optional memory context
        prompt = self._build_analysis_prompt(original_request, memory_context)
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

        response = await self.llm_client.chat_completion(request, mcp_servers=[])

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

        # Persist milestones to database with sequence offset
        await self._persist_milestones(task_id, milestones, sequence_offset)

        logger.info(
            "conductor_analysis_complete",
            task_id=str(task_id),
            milestone_count=len(milestones),
            sequence_offset=sequence_offset,
            total_tokens=response.usage.total_tokens,
        )

        return milestones

    def _build_analysis_prompt(
        self,
        original_request: str,
        memory_context: str | None = None,
    ) -> str:
        """Build prompt for task analysis.

        Args:
            original_request: User's original request
            memory_context: Optional context from long-term memory

        Returns:
            Formatted prompt for LLM
        """
        # Include memory context if available
        request_with_context = original_request
        if memory_context:
            request_with_context = (
                f"{memory_context}\n\n---\n\n## Current Request\n{original_request}"
            )

        return self.prompt_manager.render(
            "conductor",
            ConductorPrompts.ANALYSIS_PROMPT,
            original_request=request_with_context,
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
        sequence_offset: int = 0,
    ) -> None:
        """Persist milestones to database.

        Args:
            task_id: Parent task ID
            milestones: List of milestone definitions
            sequence_offset: Offset for sequence numbers (for multi-task sessions)
        """
        for i, milestone in enumerate(milestones):
            # Apply sequence offset for correct session-wide numbering
            sequence_number = sequence_offset + i + 1

            complexity_value = milestone["complexity"]
            assert isinstance(complexity_value, TaskComplexity)

            await self.milestone_repo.create(
                task_id=task_id,
                title=str(milestone.get("title", f"Milestone {sequence_number}")),
                description=str(milestone["description"]),
                complexity=complexity_value.value,
                sequence_number=sequence_number,
                acceptance_criteria=str(milestone["acceptance_criteria"]),
            )

        logger.debug(
            "milestones_persisted",
            task_id=str(task_id),
            count=len(milestones),
            sequence_offset=sequence_offset,
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

    async def replan_based_on_execution(
        self,
        task_id: UUID,
        original_request: str,
        current_milestones: list[MilestoneData],
        current_milestone_index: int,
        worker_observations: list[str],
        qa_feedback: str,
        replan_reason: str,
        previous_replans: list[dict[str, object]] | None = None,
    ) -> ConductorReplanOutput:
        """Replan milestones based on execution observations.

        Called when QA detects that the current plan needs revision based on
        observations discovered during Worker execution.

        Args:
            task_id: Task ID
            original_request: Original user request
            current_milestones: Current milestone list
            current_milestone_index: Index of milestone that triggered replan
            worker_observations: Observations from Worker execution
            qa_feedback: QA feedback that triggered replan
            replan_reason: Reason for replanning
            previous_replans: History of previous replans (for context)

        Returns:
            ConductorReplanOutput with modifications to apply

        Raises:
            ValueError: If LLM response is invalid
        """
        logger.info(
            "conductor_replan_start",
            task_id=str(task_id),
            current_milestone_index=current_milestone_index,
            replan_reason=replan_reason,
        )

        # Use MODERATE complexity for replanning (more reasoning needed than initial planning)
        model = self.router.select_model(TaskComplexity.MODERATE)

        # Build replan prompt
        prompt = self._build_replan_prompt(
            original_request=original_request,
            current_milestones=current_milestones,
            current_milestone_index=current_milestone_index,
            worker_observations=worker_observations,
            qa_feedback=qa_feedback,
            replan_reason=replan_reason,
            previous_replans=previous_replans,
        )
        messages = [ChatMessage(role="user", content=prompt)]

        # Call LLM with structured output (use dedicated replan temperature)
        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=settings.conductor_replan_temperature,
            api_base=model.api_base,
            api_key=model.api_key,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "conductor_replan_output",
                    "strict": True,
                    "schema": ConductorReplanOutput.model_json_schema(),
                },
            },
        )

        response = await self.llm_client.chat_completion(request, mcp_servers=[])

        # Parse structured response
        try:
            replan_output = ConductorReplanOutput.model_validate_json(response.content)
        except ValueError as e:
            logger.error(
                "conductor_replan_parse_failed",
                task_id=str(task_id),
                error=str(e),
                response=response.content[:500],
            )
            raise ValueError(f"Failed to parse Conductor replan response: {e}") from e

        logger.info(
            "conductor_replan_complete",
            task_id=str(task_id),
            modifications_count=len(replan_output.modifications),
            confidence=replan_output.confidence,
            total_tokens=response.usage.total_tokens,
        )

        return replan_output

    def _build_replan_prompt(
        self,
        original_request: str,
        current_milestones: list[MilestoneData],
        current_milestone_index: int,
        worker_observations: list[str],
        qa_feedback: str,
        replan_reason: str,
        previous_replans: list[dict[str, object]] | None = None,
    ) -> str:
        """Build prompt for replanning.

        Args:
            original_request: User's original request
            current_milestones: Current milestone list
            current_milestone_index: Index of current milestone
            worker_observations: Observations from Worker
            qa_feedback: QA feedback
            replan_reason: Why replan was triggered
            previous_replans: Previous replan history

        Returns:
            Formatted prompt for LLM
        """
        # Format completed milestones
        completed = []
        for i, m in enumerate(current_milestones[:current_milestone_index]):
            completed.append(f"{i + 1}. [{m['complexity'].name}] {m['description']} ✓")
        completed_text = "\n".join(completed) if completed else "None"

        # Format current milestone
        current = current_milestones[current_milestone_index]
        current_text = f"[{current['complexity'].name}] {current['description']}"

        # Format remaining milestones
        remaining = []
        for i, m in enumerate(current_milestones[current_milestone_index + 1 :]):
            idx = current_milestone_index + 1 + i + 1
            remaining.append(f"{idx}. [{m['complexity'].name}] {m['description']}")
        remaining_text = "\n".join(remaining) if remaining else "None"

        # Format observations
        observations_text = (
            "\n".join(f"- {obs}" for obs in worker_observations) if worker_observations else "None"
        )

        # Format previous replans
        replans_text = "None"
        if previous_replans:
            replans_list = []
            for replan in previous_replans:
                modifications = replan.get("modifications", [])
                modifications_count = len(modifications) if isinstance(modifications, list) else 0
                replans_list.append(
                    f"- Iteration {replan.get('iteration', '?')}: "
                    f"{replan.get('reason', 'No reason')} "
                    f"({modifications_count} modifications)"
                )
            replans_text = "\n".join(replans_list)

        return self.prompt_manager.render(
            "conductor",
            ConductorPrompts.REPLAN_PROMPT,
            original_request=original_request,
            completed_text=completed_text,
            current_milestone_index=current_milestone_index,
            current_text=current_text,
            remaining_text=remaining_text,
            observations_text=observations_text,
            qa_feedback=qa_feedback,
            replan_reason=replan_reason,
            replans_text=replans_text,
        )

    async def rethink_strategy(
        self,
        task_id: UUID,
        original_request: str,
        failed_approach: str,
        failure_reasons: list[str],
    ) -> list[dict[str, str | TaskComplexity]]:
        """Create a new plan using a completely different strategy.

        Called after the initial approach has failed and we need to try
        a fundamentally different approach to solve the user's request.

        Args:
            task_id: Task ID
            original_request: Original user request
            failed_approach: Description of the approach that failed
            failure_reasons: List of reasons why it failed

        Returns:
            New list of milestone definitions

        Raises:
            ValueError: If LLM response is invalid
        """
        logger.info(
            "conductor_rethink_strategy_start",
            task_id=str(task_id),
            failure_reason_count=len(failure_reasons),
        )

        # Use MODERATE complexity (need more reasoning for strategy change)
        model = self.router.select_model(TaskComplexity.MODERATE)

        # Format failure reasons
        failure_reasons_text = "\n".join(f"- {reason}" for reason in failure_reasons)

        # Build rethink prompt
        prompt = self.prompt_manager.render(
            "conductor",
            ConductorPrompts.RETHINK_STRATEGY_PROMPT,
            original_request=original_request,
            failed_approach=failed_approach,
            failure_reasons=failure_reasons_text,
        )
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

        response = await self.llm_client.chat_completion(request, mcp_servers=[])

        # Parse structured response
        try:
            milestones = self._parse_milestones(response.content)
        except (ValueError, KeyError) as e:
            logger.error(
                "conductor_rethink_parse_failed",
                task_id=str(task_id),
                error=str(e),
                response=response.content[:500],
            )
            raise ValueError(f"Failed to parse Conductor rethink response: {e}") from e

        logger.info(
            "conductor_rethink_strategy_complete",
            task_id=str(task_id),
            new_milestone_count=len(milestones),
            total_tokens=response.usage.total_tokens,
        )

        return milestones
