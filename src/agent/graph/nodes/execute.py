"""Worker execution node.

Supports both:
1. New flow: project_plan with tasks
2. Legacy flow: milestones list
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.core import WorkerAgent
from agent.core.artifact_extractor import ExtractionResult, extract_artifacts
from agent.db.models.artifact import Artifact
from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.db.repository.artifact_repo import ArtifactRepository
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.db.repository.project_plan_repo import ProjectPlanRepository
from agent.events import AgentActivityEvent, AgentStatus, EventType
from agent.graph.utils import get_task_by_id, get_tasks_from_plan, update_task_status
from agent.llm import ChatMessage
from agent.llm.schemas import WorkerReActOutput

from ..state import AgentState, MilestoneData, update_milestone
from . import check_task_cancelled, get_container, get_event_bus, get_ws_manager_optional

logger = structlog.get_logger()


def _get_artifact_key(artifact: Artifact) -> str:
    """Generate consistent key for artifact deduplication.

    Args:
        artifact: Artifact model instance

    Returns:
        Normalized path key for deduplication
    """
    path = artifact.path.strip("/") if artifact.path else ""
    return f"{path}/{artifact.filename}" if path else artifact.filename


async def _load_artifacts_for_context(
    artifact_repo: ArtifactRepository,
    task_id: UUID,
    session_id: UUID,
) -> tuple[list[Artifact], list[Artifact], list[Artifact]]:
    """Load and merge artifacts for Worker context.

    Loads current task artifacts and previous snapshot, then merges them
    with current task taking precedence.

    Args:
        artifact_repo: Artifact repository instance
        task_id: Current task UUID
        session_id: Session UUID

    Returns:
        Tuple of (current_task_artifacts, previous_snapshot, merged_artifacts)
    """
    current_task_artifacts = await artifact_repo.get_by_task_id(task_id)
    previous_snapshot = await artifact_repo.get_latest_snapshot(session_id)

    # Merge: current task artifacts override previous snapshot
    artifact_map: dict[str, Artifact] = {}
    for artifact in previous_snapshot:
        key = _get_artifact_key(artifact)
        artifact_map[key] = artifact
    for artifact in current_task_artifacts:
        key = _get_artifact_key(artifact)
        artifact_map[key] = artifact

    merged_artifacts = list(artifact_map.values())
    return current_task_artifacts, previous_snapshot, merged_artifacts


def _build_artifacts_context_message(artifacts: list[Artifact]) -> ChatMessage | None:
    """Build context message with artifact file list.

    Creates a lightweight file list instead of full content to save tokens.
    Worker can use read_artifact tool to fetch full content when needed.

    Args:
        artifacts: List of artifacts to include in context

    Returns:
        ChatMessage with artifact list, or None if no artifacts
    """
    if not artifacts:
        return None

    file_list = []
    total_chars = 0
    for artifact in artifacts:
        file_path = _get_artifact_key(artifact)
        file_list.append(f"- {file_path} ({artifact.kind}, {len(artifact.content)} chars)")
        total_chars += len(artifact.content)

    content = (
        "## Session Files\n"
        f"Total: {len(artifacts)} files, ~{total_chars} chars\n\n" + "\n".join(file_list)
    )
    return ChatMessage(role="system", content=content)


async def _copy_previous_snapshot_to_task(
    artifact_repo: ArtifactRepository,
    session_id: UUID,
    task_id: UUID,
    previous_snapshot: list[Artifact],
) -> None:
    """Copy previous task's artifacts as baseline for new task.

    This ensures files not modified in this task are preserved.

    Args:
        artifact_repo: Artifact repository instance
        session_id: Session UUID
        task_id: Current task UUID
        previous_snapshot: Artifacts from previous task
    """
    baseline_artifacts = [
        {
            "artifact_type": a.artifact_type,
            "filename": a.filename,
            "kind": a.kind,
            "content": a.content,
            "path": a.path or "",
            "sequence_number": a.sequence_number,
        }
        for a in previous_snapshot
    ]
    await artifact_repo.save_task_snapshot(
        session_id=session_id,
        task_id=task_id,
        milestone_id=None,  # No milestone for baseline copy
        artifacts=baseline_artifacts,
    )
    logger.info(
        "previous_artifacts_copied_to_task",
        task_id=str(task_id),
        count=len(baseline_artifacts),
    )


async def _save_milestone_artifacts(
    artifact_repo: ArtifactRepository,
    session_id: UUID,
    task_id: UUID,
    milestone_id: UUID,
    extraction_result: ExtractionResult,
    previous_snapshot: list[Artifact],
    milestone_repo: MilestoneRepository | None = None,
) -> list[dict[str, Any]]:
    """Save artifacts from milestone extraction result.

    Handles baseline copy, deletions, and new artifacts.

    Args:
        artifact_repo: Artifact repository instance
        session_id: Session UUID
        task_id: Current task UUID
        milestone_id: Current milestone UUID
        extraction_result: Extracted artifacts and deletion paths
        previous_snapshot: Previous task's artifacts for baseline copy
        milestone_repo: Optional milestone repository for validation

    Returns:
        List of artifact dicts for broadcast
    """
    # Validate milestone exists before using its ID for FK constraint
    validated_milestone_id: UUID | None = milestone_id
    if milestone_repo is not None:
        milestone = await milestone_repo.get_by_id(milestone_id)
        if milestone is None:
            logger.warning(
                "milestone_not_found_for_artifacts",
                milestone_id=str(milestone_id),
                task_id=str(task_id),
                message="Milestone not found in DB, saving artifacts without milestone_id",
            )
            validated_milestone_id = None

    # On first milestone, copy previous task's artifacts as baseline
    current_task_artifact_count = len(await artifact_repo.get_by_task_id(task_id))
    if current_task_artifact_count == 0 and previous_snapshot:
        await _copy_previous_snapshot_to_task(artifact_repo, session_id, task_id, previous_snapshot)

    # Handle explicit file deletions first
    if extraction_result.deleted_paths:
        deleted_count = await artifact_repo.delete_by_paths(
            task_id=task_id,
            paths=extraction_result.deleted_paths,
        )
        logger.info(
            "artifacts_deleted",
            task_id=str(task_id),
            milestone_id=str(milestone_id),
            deleted_paths=extraction_result.deleted_paths,
            count=deleted_count,
        )

    # Save new/updated artifacts
    if extraction_result.artifacts:
        artifacts_data = [
            {
                "artifact_type": artifact.artifact_type,
                "filename": artifact.filename,
                "kind": artifact.kind,
                "content": artifact.content,
                "path": artifact.path,
                "sequence_number": artifact.sequence_number,
            }
            for artifact in extraction_result.artifacts
        ]

        await artifact_repo.save_task_snapshot(
            session_id=session_id,
            task_id=task_id,
            milestone_id=validated_milestone_id,
            artifacts=artifacts_data,
        )

        logger.info(
            "artifacts_saved_for_milestone",
            milestone_id=str(validated_milestone_id),
            task_id=str(task_id),
            count=len(extraction_result.artifacts),
        )

    # Get ALL artifacts for broadcast
    all_task_artifacts = await artifact_repo.get_by_task_id(task_id)
    return [
        {
            "id": str(a.id),
            "type": a.artifact_type,
            "filename": a.filename,
            "kind": a.kind,
            "language": a.kind,  # Frontend expects 'language' field
            "content": a.content,
            "path": a.path,
        }
        for a in all_task_artifacts
    ]


def _prepare_worker_prompt(
    state: AgentState,
    milestone: MilestoneData,
) -> str:
    """Prepare prompt for Worker execution.

    Args:
        state: Current workflow state
        milestone: Current milestone data

    Returns:
        Prepared prompt string
    """
    base_prompt = state.get("current_prompt") or milestone["description"]
    original_request = state.get("original_request", "")

    # Prepend original request if not already included
    if original_request and original_request not in base_prompt:
        return f"Original user request:\n{original_request}\n\nCurrent task:\n{base_prompt}"
    return base_prompt


def _prepare_worker_prompt_from_task(
    state: AgentState,
    task: dict[str, Any],
) -> str:
    """Prepare prompt for Worker execution from project plan task.

    Args:
        state: Current workflow state
        task: Current task dict from project_plan

    Returns:
        Prepared prompt string
    """
    base_prompt = state.get("current_prompt") or task.get("description", "")
    original_request = state.get("original_request", "")
    acceptance_criteria = task.get("acceptance_criteria", "")

    # Build comprehensive prompt with task details
    prompt_parts = []

    if original_request and original_request not in base_prompt:
        prompt_parts.append(f"Original user request:\n{original_request}")

    prompt_parts.append(f"Current task:\n{base_prompt}")

    if acceptance_criteria:
        prompt_parts.append(f"Acceptance criteria:\n{acceptance_criteria}")

    return "\n\n".join(prompt_parts)


def _get_complexity_from_task(task: dict[str, Any]) -> TaskComplexity:
    """Extract complexity from task dict.

    Args:
        task: Task dict from project_plan

    Returns:
        TaskComplexity enum value
    """
    complexity_str = task.get("complexity", "MODERATE")
    try:
        return TaskComplexity[complexity_str]
    except KeyError:
        return TaskComplexity.MODERATE


def _extract_react_observations(worker_output: str) -> list[str]:
    """Extract ReAct observations from worker output.

    Attempts to parse output as WorkerReActOutput to extract observations
    and discovered issues. Falls back to empty list if parsing fails.

    Args:
        worker_output: Raw worker output string

    Returns:
        List of observations (combined observations and discovered_issues)
    """
    try:
        react_output = WorkerReActOutput.model_validate_json(worker_output)
        observations = list(react_output.observations)
        observations.extend(react_output.discovered_issues)
        return observations
    except Exception:
        # Not a ReAct output format, return empty list
        return []


async def execute_worker_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Execute task/milestone via Worker agent.

    Handles both fresh execution and retry scenarios,
    passing QA feedback for retries.

    Supports both:
    - New flow: project_plan with tasks
    - Legacy flow: milestones list

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with worker output and updated context
    """
    container = get_container(config)
    event_bus = get_event_bus(config)
    ws_manager = get_ws_manager_optional(config)

    # Check if task was cancelled
    if await check_task_cancelled(session, state["task_id"]):
        logger.info("execute_worker_cancelled", task_id=str(state["task_id"]))
        return {
            "error": "Task cancelled by user",
            "error_node": "execute_worker",
            "task_status": TaskStatus.FAILED,
            "workflow_complete": True,
        }

    try:
        # Check if using new project_plan flow or legacy milestones flow
        project_plan = state.get("project_plan")
        milestones = state.get("milestones")
        idx = state.get("current_milestone_index")

        logger.debug(
            "execute_worker_context",
            user_id=state["user_id"],
            session_id=str(state["session_id"]),
            task_id=str(state["task_id"]),
            has_project_plan=project_plan is not None,
        )

        # Extract task information based on flow type
        if project_plan:
            current_task_id: str | None = state.get("current_task_id")  # type: ignore[assignment]
            tasks = get_tasks_from_plan(project_plan)
            task = get_task_by_id(tasks, current_task_id) if current_task_id else None

            if task is None:
                return {
                    "error": "No task available in project plan",
                    "error_node": "execute_worker",
                }

            # Create milestone-like dict for compatibility
            task_complexity = _get_complexity_from_task(task)
            milestone: MilestoneData = {
                "id": state["task_id"],  # Use task_id as milestone_id for events
                "description": task.get("description", ""),
                "complexity": task_complexity,
                "acceptance_criteria": task.get("acceptance_criteria", ""),
                "status": MilestoneStatus.IN_PROGRESS,
                "selected_model": None,
                "generated_prompt": None,
                "worker_output": None,
                "qa_feedback": None,
                "retry_count": state.get("retry_count", 0),
            }
            idx = idx if idx is not None else 0
        else:
            if milestones is None or idx is None:
                return {"error": "No milestones available", "error_node": "execute_worker"}
            milestone = milestones[idx]
            task = None

        retry_count = state.get("retry_count", 0)

        # Emit worker started event
        message = (
            "Executing task" if retry_count == 0 else f"Retrying task (attempt {retry_count + 1})"
        )
        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_STARTED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=milestone["id"],
                sequence_number=idx + 1,
                agent="worker",
                status=AgentStatus.STARTED,
                message=message,
            )
        )

        # Initialize worker and artifact repo
        worker = WorkerAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
            ws_manager=ws_manager,
        )
        artifact_repo = ArtifactRepository(session)

        # Load artifacts for context
        current_task_artifacts, previous_snapshot, merged_artifacts = (
            await _load_artifacts_for_context(artifact_repo, state["task_id"], state["session_id"])
        )

        # Build context messages
        context_messages = list(state.get("context_messages", []))
        artifacts_context = _build_artifacts_context_message(merged_artifacts)
        if artifacts_context:
            # Remove any previous artifact context
            context_messages = [
                msg
                for msg in context_messages
                if not (msg.role == "system" and "Artifacts" in msg.content)
            ]
            context_messages.insert(0, artifacts_context)
            logger.info(
                "artifacts_loaded_for_context",
                task_id=str(state["task_id"]),
                current_task_count=len(current_task_artifacts),
                previous_snapshot_count=len(previous_snapshot),
                merged_count=len(merged_artifacts),
            )

        # Prepare prompt and execute
        if project_plan and task:
            prompt = _prepare_worker_prompt_from_task(state, task)
        else:
            prompt = _prepare_worker_prompt(state, milestone)
        previous_output = milestone.get("worker_output")
        qa_feedback = state.get("current_qa_feedback")

        if retry_count > 0 and previous_output and qa_feedback:
            response = await worker.retry_with_feedback(
                milestone_id=milestone["id"],
                original_prompt=prompt,
                previous_output=previous_output,
                qa_feedback=qa_feedback,
                complexity=milestone["complexity"],
                user_id=state["user_id"],
                session_id=state["session_id"],
                task_id=state["task_id"],
            )
        else:
            response = await worker.execute_milestone(
                milestone_id=milestone["id"],
                prompt=prompt,
                complexity=milestone["complexity"],
                user_id=state["user_id"],
                session_id=state["session_id"],
                task_id=state["task_id"],
                preferred_model=milestone.get("selected_model"),
                context_messages=context_messages,
            )

        # Update milestone with output (for legacy flow)
        updated_milestones = None
        if milestones:
            updated_milestones = list(milestones)
            updated_milestones[idx] = update_milestone(milestone, worker_output=response.content)

        # Update project_plan task status (for new flow)
        updated_project_plan = None
        if project_plan and task:
            plan_current_task_id: str | None = state.get("current_task_id")  # type: ignore[assignment]
            if plan_current_task_id:
                updated_plan_data = update_task_status(
                    project_plan.plan_data,
                    plan_current_task_id,
                    "in_progress",
                )
                # Note: We update to in_progress here; completion happens in advance node
                project_plan.plan_data = updated_plan_data
                updated_project_plan = project_plan

        # Update context with new exchange
        context_messages = list(state.get("context_messages", []))
        context_messages.append(ChatMessage(role="user", content=prompt))
        context_messages.append(ChatMessage(role="assistant", content=response.content))

        # Calculate tokens and cost
        current_tokens = state.get("current_context_tokens", 0) + response.usage.total_tokens
        total_input = state.get("total_input_tokens", 0) + response.usage.input_tokens
        total_output = state.get("total_output_tokens", 0) + response.usage.output_tokens

        model = container.router.select_model(
            complexity=milestone["complexity"],
            preferred_model=milestone.get("selected_model"),
        )
        call_cost = container.router.calculate_cost(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        total_cost = Decimal(state.get("total_cost_usd", "0")) + call_cost

        logger.info(
            "worker_executed",
            milestone_index=idx,
            output_length=len(response.content),
            tokens=response.usage.total_tokens,
            cost_usd=float(call_cost),
            is_retry=retry_count > 0,
            finish_reason=response.finish_reason,
        )

        # Check if response was truncated
        if response.finish_reason == "length":
            logger.error(
                "worker_response_truncated",
                milestone_id=str(milestone["id"]),
                output_length=len(response.content),
                message="Worker response was cut off due to token limit",
            )
            truncated_result: dict[str, Any] = {
                "error": "Worker response was truncated due to token limit.",
                "error_node": "execute_worker",
                "current_output": response.content,
            }
            if updated_milestones:
                truncated_result["milestones"] = updated_milestones
            if updated_project_plan:
                truncated_result["project_plan"] = updated_project_plan
            return truncated_result

        # Update milestone in DB (only for legacy flow with real milestones)
        milestone_repo = MilestoneRepository(session)
        if not project_plan and milestones:
            await milestone_repo.update_llm_usage(
                milestone_id=milestone["id"],
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cost=call_cost,
            )
            await milestone_repo.update(
                milestone["id"],
                selected_llm=model.name,
                worker_output=response.content,
            )
        elif project_plan:
            # For project_plan flow, persist plan data update
            plan_repo = ProjectPlanRepository(session)
            await plan_repo.update(project_plan.id, plan_data=project_plan.plan_data)
            await session.commit()

        # Extract and save artifacts
        extraction_result = extract_artifacts(response.content)

        if not extraction_result.artifacts and response.content.strip().startswith("{"):
            logger.warning(
                "artifact_extraction_empty",
                milestone_id=str(milestone["id"]),
                content_length=len(response.content),
                message="No artifacts extracted, JSON parsing may have failed",
            )

        # For project_plan flow, pass None for milestone_repo to skip milestone validation
        artifacts_for_broadcast = await _save_milestone_artifacts(
            artifact_repo=artifact_repo,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone["id"],
            extraction_result=extraction_result,
            previous_snapshot=previous_snapshot,
            milestone_repo=milestone_repo if not project_plan else None,
        )

        # Build and emit worker completed event
        output_preview = (
            response.content[:500] + "..." if len(response.content) > 500 else response.content
        )
        worker_details = {
            "output": response.content,
            "output_preview": output_preview,
            "output_length": len(response.content),
            "tokens_used": response.usage.total_tokens,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "model": model.name,
            "cost_usd": float(call_cost),
            "is_retry": retry_count > 0,
            "artifacts": artifacts_for_broadcast,
        }

        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_COMPLETED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=milestone["id"],
                sequence_number=idx + 1,
                agent="worker",
                status=AgentStatus.COMPLETED,
                message=f"Task executed ({response.usage.total_tokens} tokens)",
                details=worker_details,
            )
        )

        # Extract ReAct observations for potential replanning (if enabled)
        settings = get_agent_settings()
        current_observations = state.get("current_observations", [])
        if settings.enable_react_observations:
            observations = _extract_react_observations(response.content)
            if observations:
                current_observations = [*current_observations, *observations]
                logger.info(
                    "react_observations_extracted",
                    milestone_id=str(milestone["id"]),
                    observation_count=len(observations),
                )

        # Build result with flow-specific fields
        result: dict[str, Any] = {
            "current_output": response.content,
            "context_messages": context_messages,
            "current_context_tokens": current_tokens,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": str(total_cost),
            "current_observations": current_observations,
        }

        if updated_milestones:
            result["milestones"] = updated_milestones

        if updated_project_plan:
            result["project_plan"] = updated_project_plan

        return result

    except Exception as e:
        logger.error("execute_worker_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "execute_worker",
        }


async def create_task_executor(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> Callable[[str], Awaitable[dict[str, Any]]]:
    """Create a task executor function for parallel execution.

    Returns a callable that can be used by ExecutionEngine to execute
    individual tasks by their ID.

    This function is a factory that creates task executors bound to the
    current state, config, and session.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Async callable that takes task_id and returns execution result dict.
        The result dict contains:
        - success: bool - Whether execution succeeded
        - output: str - Worker output content
        - error: str | None - Error message if failed
        - tokens_used: int - Total tokens consumed
        - cost_usd: str - Execution cost

    Example:
        >>> executor = await create_task_executor(state, config, session)
        >>> result = await executor("T1.1.1")
        >>> if result["success"]:
        ...     print(f"Output: {result['output']}")
    """
    container = get_container(config)
    event_bus = get_event_bus(config)
    ws_manager = get_ws_manager_optional(config)
    project_plan = state.get("project_plan")

    if not project_plan:
        raise ValueError("create_task_executor requires project_plan in state")

    tasks = get_tasks_from_plan(project_plan)

    async def task_executor(task_id: str) -> dict[str, Any]:
        """Execute a single task by ID.

        Args:
            task_id: Task ID from project plan (e.g., "T1.1.1")

        Returns:
            Execution result dict with success, output, error, tokens_used, cost_usd
        """
        task = get_task_by_id(tasks, task_id)

        if task is None:
            logger.error("task_not_found_for_execution", task_id=task_id)
            return {
                "success": False,
                "output": "",
                "error": f"Task {task_id} not found in project plan",
                "tokens_used": 0,
                "cost_usd": "0",
            }

        try:
            # Get task complexity
            complexity = _get_complexity_from_task(task)

            # Build milestone-like dict for compatibility
            milestone: MilestoneData = {
                "id": state["task_id"],  # Use workflow task_id
                "description": task.get("description", ""),
                "complexity": complexity,
                "acceptance_criteria": task.get("acceptance_criteria", ""),
                "status": MilestoneStatus.IN_PROGRESS,
                "selected_model": None,
                "generated_prompt": None,
                "worker_output": None,
                "qa_feedback": None,
                "retry_count": 0,
            }

            # Emit worker started event for this task
            await event_bus.emit(
                AgentActivityEvent(
                    type=EventType.AGENT_STARTED,
                    session_id=state["session_id"],
                    task_id=state["task_id"],
                    milestone_id=milestone["id"],
                    sequence_number=0,  # Parallel execution doesn't use sequential numbering
                    agent="worker",
                    status=AgentStatus.STARTED,
                    message=f"Executing task {task_id}",
                    details={"parallel_task_id": task_id},
                )
            )

            # Initialize worker
            worker = WorkerAgent(
                llm_client=container.llm_client,
                router=container.router,
                prompt_manager=container.prompt_manager,
                session=session,
                ws_manager=ws_manager,
            )
            artifact_repo = ArtifactRepository(session)

            # Load artifacts for context
            _, _, merged_artifacts = await _load_artifacts_for_context(
                artifact_repo, state["task_id"], state["session_id"]
            )

            # Build context messages
            context_messages = list(state.get("context_messages", []))
            artifacts_context = _build_artifacts_context_message(merged_artifacts)
            if artifacts_context:
                context_messages = [
                    msg
                    for msg in context_messages
                    if not (msg.role == "system" and "Artifacts" in msg.content)
                ]
                context_messages.insert(0, artifacts_context)

            # Prepare prompt
            prompt = _prepare_worker_prompt_from_task(state, task)

            # Execute task
            response = await worker.execute_milestone(
                milestone_id=milestone["id"],
                prompt=prompt,
                complexity=complexity,
                user_id=state["user_id"],
                session_id=state["session_id"],
                task_id=state["task_id"],
                preferred_model=None,
                context_messages=context_messages,
            )

            # Calculate cost
            model = container.router.select_model(complexity=complexity)
            call_cost = container.router.calculate_cost(
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            logger.info(
                "parallel_task_executed",
                task_id=task_id,
                output_length=len(response.content),
                tokens=response.usage.total_tokens,
                cost_usd=float(call_cost),
            )

            # Emit worker completed event
            await event_bus.emit(
                AgentActivityEvent(
                    type=EventType.AGENT_COMPLETED,
                    session_id=state["session_id"],
                    task_id=state["task_id"],
                    milestone_id=milestone["id"],
                    sequence_number=0,
                    agent="worker",
                    status=AgentStatus.COMPLETED,
                    message=f"Task {task_id} completed ({response.usage.total_tokens} tokens)",
                    details={
                        "parallel_task_id": task_id,
                        "output_length": len(response.content),
                        "tokens_used": response.usage.total_tokens,
                        "cost_usd": float(call_cost),
                    },
                )
            )

            return {
                "success": True,
                "output": response.content,
                "error": None,
                "tokens_used": response.usage.total_tokens,
                "cost_usd": str(call_cost),
            }

        except Exception as e:
            logger.error("parallel_task_failed", task_id=task_id, error=str(e))

            # Emit worker failed event
            await event_bus.emit(
                AgentActivityEvent(
                    type=EventType.AGENT_FAILED,
                    session_id=state["session_id"],
                    task_id=state["task_id"],
                    milestone_id=state["task_id"],
                    sequence_number=0,
                    agent="worker",
                    status=AgentStatus.FAILED,
                    message=f"Task {task_id} failed: {e}",
                    details={"parallel_task_id": task_id, "error": str(e)},
                )
            )

            return {
                "success": False,
                "output": "",
                "error": str(e),
                "tokens_used": 0,
                "cost_usd": "0",
            }

    return task_executor


__all__ = [
    "execute_worker_node",
    "create_task_executor",
]
