"""Architect Agent for hierarchical project planning.

The Architect is responsible for:
1. Analyzing user requests and determining project complexity
2. Creating hierarchical project plans (Epic > Feature > Task)
3. Identifying dependencies and parallelizable tasks
4. Revising plans based on user feedback
5. Replanning during execution based on observations
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import TaskComplexity
from agent.db.repository.project_plan_repo import ProjectPlanRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMRouter
from agent.llm.schemas import (
    ArchitectReplanOutput,
    ProjectPlanOutput,
)
from agent.prompts import ArchitectPrompts, PromptManager

if TYPE_CHECKING:
    from agent.db.models.project_plan import ProjectPlan

logger = structlog.get_logger()


class ArchitectAgent:
    """Architect agent for hierarchical project planning.

    Creates structured project plans with Epic > Feature > Task hierarchy
    based on project complexity. Supports plan revision based on user
    feedback and dynamic replanning during execution.
    """

    def __init__(
        self,
        llm_client: LiteLLMClient,
        router: LLMRouter,
        prompt_manager: PromptManager,
        session: AsyncSession,
    ) -> None:
        """Initialize Architect agent.

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
        self.plan_repo = ProjectPlanRepository(session)

    async def create_plan(
        self,
        task_id: UUID,
        session_id: UUID,
        original_request: str,
        memory_context: str | None = None,
        project_context: str | None = None,
    ) -> ProjectPlan:
        """Create hierarchical project plan from user request.

        Analyzes the complexity of the request and creates an appropriate
        plan structure (flat, grouped, or hierarchical).

        Args:
            task_id: Task ID to associate plan with
            session_id: Session ID
            original_request: Original user request
            memory_context: Optional context from long-term memory
            project_context: Optional project/codebase context

        Returns:
            Created ProjectPlan database instance

        Raises:
            ValueError: If LLM response is invalid
        """
        logger.info(
            "architect_planning_start",
            task_id=str(task_id),
            session_id=str(session_id),
            request_length=len(original_request),
            has_memory_context=bool(memory_context),
            has_project_context=bool(project_context),
        )

        # Use MODERATE complexity for planning (requires reasoning)
        model = self.router.select_model(TaskComplexity.MODERATE)

        # Build planning prompt
        prompt = self._build_planning_prompt(
            original_request=original_request,
            memory_context=memory_context,
            project_context=project_context,
        )
        messages = [ChatMessage(role="user", content=prompt)]

        # Call LLM with structured output
        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=settings.conductor_temperature,  # Reuse conductor temp for consistency
            api_base=model.api_base,
            api_key=model.api_key,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "project_plan_output",
                    "strict": True,
                    "schema": ProjectPlanOutput.model_json_schema(),
                },
            },
        )

        response = await self.llm_client.chat_completion(request, mcp_servers=[])

        # Parse and validate response
        try:
            output = ProjectPlanOutput.model_validate_json(response.content)
        except ValueError as e:
            logger.error(
                "architect_parse_failed",
                task_id=str(task_id),
                error=str(e),
                response=response.content[:500],
            )
            raise ValueError(f"Failed to parse Architect response: {e}") from e

        # Count total tasks
        total_tasks = self._count_total_tasks(output)

        # Persist plan to database
        project_plan = await self.plan_repo.create(
            task_id=task_id,
            session_id=session_id,
            title=output.title,
            overview=output.overview,
            tech_stack=output.tech_stack,
            structure_type=output.structure_type,
            plan_data=self._convert_output_to_plan_data(output),
            status="draft",
            total_tasks=total_tasks,
        )

        logger.info(
            "architect_planning_complete",
            task_id=str(task_id),
            plan_id=str(project_plan.id),
            structure_type=output.structure_type,
            total_tasks=total_tasks,
            total_tokens=response.usage.total_tokens,
        )

        return project_plan

    async def revise_plan(
        self,
        plan_id: UUID,
        user_feedback: str,
    ) -> ProjectPlan:
        """Revise plan based on user feedback.

        Supports human-in-the-loop workflow by allowing users to request
        changes to the plan before approval.

        Args:
            plan_id: Plan ID to revise
            user_feedback: User's revision feedback

        Returns:
            Updated ProjectPlan database instance

        Raises:
            ValueError: If plan not found or LLM response is invalid
        """
        # Get current plan
        current_plan = await self.plan_repo.get_by_id(plan_id)
        if not current_plan:
            raise ValueError(f"Plan not found: {plan_id}")

        logger.info(
            "architect_revise_start",
            plan_id=str(plan_id),
            task_id=str(current_plan.task_id),
            feedback_length=len(user_feedback),
        )

        # Use MODERATE complexity for revision (requires reasoning)
        model = self.router.select_model(TaskComplexity.MODERATE)

        # Build revise prompt
        prompt = self._build_revise_prompt(
            original_request=self._get_original_request_from_plan(current_plan),
            current_plan=current_plan.plan_data,
            user_feedback=user_feedback,
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
                    "name": "project_plan_output",
                    "strict": True,
                    "schema": ProjectPlanOutput.model_json_schema(),
                },
            },
        )

        response = await self.llm_client.chat_completion(request, mcp_servers=[])

        # Parse and validate response
        try:
            output = ProjectPlanOutput.model_validate_json(response.content)
        except ValueError as e:
            logger.error(
                "architect_revise_parse_failed",
                plan_id=str(plan_id),
                error=str(e),
                response=response.content[:500],
            )
            raise ValueError(f"Failed to parse Architect revise response: {e}") from e

        # Count total tasks
        total_tasks = self._count_total_tasks(output)

        # Update plan in database
        updated_plan = await self.plan_repo.update(
            plan_id,
            title=output.title,
            overview=output.overview,
            tech_stack=output.tech_stack,
            structure_type=output.structure_type,
            plan_data=self._convert_output_to_plan_data(output),
            total_tasks=total_tasks,
            # Reset progress since plan changed
            completed_tasks=0,
            failed_tasks=0,
        )

        logger.info(
            "architect_revise_complete",
            plan_id=str(plan_id),
            structure_type=output.structure_type,
            total_tasks=total_tasks,
            total_tokens=response.usage.total_tokens,
        )

        return updated_plan  # type: ignore[return-value]

    async def replan_on_execution(
        self,
        plan_id: UUID,
        current_task_id: str,
        execution_issue: str,
        worker_observations: list[str],
        completed_tasks: list[str] | None = None,
    ) -> ArchitectReplanOutput:
        """Adjust plan based on execution observations.

        Called when issues arise during task execution that may require
        plan modifications.

        Args:
            plan_id: Plan ID
            current_task_id: Current task ID (e.g., "T1.1.1")
            execution_issue: What went wrong
            worker_observations: Observations from Worker execution
            completed_tasks: List of completed task IDs

        Returns:
            ArchitectReplanOutput with analysis and modifications

        Raises:
            ValueError: If plan not found or LLM response is invalid
        """
        # Get current plan
        current_plan = await self.plan_repo.get_by_id(plan_id)
        if not current_plan:
            raise ValueError(f"Plan not found: {plan_id}")

        logger.info(
            "architect_replan_start",
            plan_id=str(plan_id),
            current_task_id=current_task_id,
            issue_length=len(execution_issue),
            observation_count=len(worker_observations),
        )

        # Use MODERATE complexity for replanning (requires deep reasoning)
        model = self.router.select_model(TaskComplexity.MODERATE)

        # Build replan prompt
        prompt = self._build_replan_prompt(
            original_request=self._get_original_request_from_plan(current_plan),
            plan_status=current_plan.status,
            completed_tasks=completed_tasks or [],
            current_task_id=current_task_id,
            execution_issue=execution_issue,
            worker_observations=worker_observations,
            plan_data=current_plan.plan_data,
        )
        messages = [ChatMessage(role="user", content=prompt)]

        # Call LLM with structured output
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
                    "name": "architect_replan_output",
                    "strict": True,
                    "schema": ArchitectReplanOutput.model_json_schema(),
                },
            },
        )

        response = await self.llm_client.chat_completion(request, mcp_servers=[])

        # Parse and validate response
        try:
            replan_output = ArchitectReplanOutput.model_validate_json(response.content)
        except ValueError as e:
            logger.error(
                "architect_replan_parse_failed",
                plan_id=str(plan_id),
                error=str(e),
                response=response.content[:500],
            )
            raise ValueError(f"Failed to parse Architect replan response: {e}") from e

        logger.info(
            "architect_replan_complete",
            plan_id=str(plan_id),
            action=replan_output.action,
            modifications_count=len(replan_output.modifications or []),
            confidence=replan_output.confidence,
            total_tokens=response.usage.total_tokens,
        )

        return replan_output

    def _build_planning_prompt(
        self,
        original_request: str,
        memory_context: str | None = None,
        project_context: str | None = None,
    ) -> str:
        """Build prompt for project planning.

        Args:
            original_request: User's original request
            memory_context: Optional context from long-term memory
            project_context: Optional project/codebase context

        Returns:
            Formatted prompt for LLM
        """
        return self.prompt_manager.render(
            "architect",
            ArchitectPrompts.PLANNING_PROMPT,
            original_request=original_request,
            memory_context=memory_context,
            project_context=project_context,
        )

    def _build_revise_prompt(
        self,
        original_request: str,
        current_plan: dict[str, Any],
        user_feedback: str,
    ) -> str:
        """Build prompt for plan revision.

        Args:
            original_request: User's original request
            current_plan: Current plan data as dict
            user_feedback: User's revision feedback

        Returns:
            Formatted prompt for LLM
        """
        import json

        return self.prompt_manager.render(
            "architect",
            ArchitectPrompts.REVISE_PROMPT,
            original_request=original_request,
            current_plan=json.dumps(current_plan, indent=2),
            user_feedback=user_feedback,
        )

    def _build_replan_prompt(
        self,
        original_request: str,
        plan_status: str,
        completed_tasks: list[str],
        current_task_id: str,
        execution_issue: str,
        worker_observations: list[str],
        plan_data: dict[str, Any],
    ) -> str:
        """Build prompt for execution replanning.

        Args:
            original_request: User's original request
            plan_status: Current plan status
            completed_tasks: List of completed task IDs
            current_task_id: Current task ID
            execution_issue: Description of the issue
            worker_observations: Observations from Worker

        Returns:
            Formatted prompt for LLM
        """
        # Format completed tasks
        completed_text = "\n".join(f"- {task_id}" for task_id in completed_tasks)
        if not completed_text:
            completed_text = "None"

        # Format current task info
        current_task = self._find_task_in_plan_data(plan_data, current_task_id)
        current_task_text = (
            f"{current_task_id}: {current_task.get('description', 'Unknown')}"
            if current_task
            else current_task_id
        )

        # Format observations
        observations_text = "\n".join(f"- {obs}" for obs in worker_observations)
        if not observations_text:
            observations_text = "None"

        return self.prompt_manager.render(
            "architect",
            ArchitectPrompts.REPLAN_PROMPT,
            original_request=original_request,
            plan_status=plan_status,
            completed_tasks=completed_text,
            current_task=current_task_text,
            execution_issue=execution_issue,
            worker_observations=observations_text,
        )

    def _convert_output_to_plan_data(self, output: ProjectPlanOutput) -> dict[str, Any]:
        """Convert LLM output to plan_data dict for storage.

        Args:
            output: Parsed ProjectPlanOutput from LLM

        Returns:
            Dict suitable for JSONB storage
        """
        return {
            "epics": [e.model_dump() for e in output.epics] if output.epics else None,
            "features": [f.model_dump() for f in output.features] if output.features else None,
            "tasks": [t.model_dump() for t in output.tasks],
        }

    def _count_total_tasks(self, output: ProjectPlanOutput) -> int:
        """Count total tasks in the plan output.

        Args:
            output: Parsed ProjectPlanOutput from LLM

        Returns:
            Total number of tasks
        """
        return len(output.tasks)

    def _count_parallelizable_tasks(self, output: ProjectPlanOutput) -> int:
        """Count tasks that can run in parallel (no dependencies).

        Args:
            output: Parsed ProjectPlanOutput from LLM

        Returns:
            Number of tasks with no dependencies
        """
        return len([t for t in output.tasks if not t.dependencies])

    def _get_original_request_from_plan(self, plan: ProjectPlan) -> str:
        """Extract original request from plan data or overview.

        Args:
            plan: ProjectPlan instance

        Returns:
            Original request string or overview as fallback
        """
        # Plan data might store original_request
        if plan.plan_data and "original_request" in plan.plan_data:
            return str(plan.plan_data["original_request"])
        # Fall back to overview
        return plan.overview or plan.title

    def _find_task_in_plan_data(
        self,
        plan_data: dict[str, Any],
        task_id: str,
    ) -> dict[str, Any] | None:
        """Find a task by ID in plan data.

        Args:
            plan_data: Plan data dict
            task_id: Task ID to find

        Returns:
            Task dict or None if not found
        """
        tasks: list[dict[str, Any]] = plan_data.get("tasks", [])
        for task in tasks:
            if task.get("id") == task_id:
                return task
        return None
