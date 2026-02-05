"""Worker execution node.

Executes tasks from project_plan using the Worker agent.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, TypedDict
from uuid import UUID

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import WorkerAgent
from agent.core.artifact_extractor import ExtractionResult, extract_artifacts
from agent.db.models.artifact import Artifact
from agent.db.models.enums import TaskComplexity, TaskStatus
from agent.db.repository.artifact_repo import ArtifactRepository
from agent.db.repository.project_plan_repo import ProjectPlanRepository
from agent.events import AgentActivityEvent, AgentStatus, EventType
from agent.graph.utils import get_task_by_id, get_tasks_from_plan, update_task_status
from agent.llm import ChatMessage

from ..state import AgentState
from . import check_task_cancelled, get_container, get_event_bus, get_ws_manager_optional

logger = structlog.get_logger()


class TaskData(TypedDict):
    """Task data structure for Worker execution."""

    id: str
    description: str
    complexity: TaskComplexity
    acceptance_criteria: str
    worker_output: str | None
    retry_count: int


def _get_artifact_key(artifact: Artifact) -> str:
    """Generate consistent key for artifact deduplication."""
    path = artifact.path.strip("/") if artifact.path else ""
    return f"{path}/{artifact.filename}" if path else artifact.filename


async def _load_artifacts_for_context(
    artifact_repo: ArtifactRepository,
    task_id: UUID,
    session_id: UUID,
) -> tuple[list[Artifact], list[Artifact], list[Artifact]]:
    """Load and merge artifacts for Worker context."""
    current_task_artifacts = await artifact_repo.get_by_task_id(task_id)
    previous_snapshot = await artifact_repo.get_latest_snapshot(session_id)

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
    """Build context message with artifact file list."""
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
    """Copy previous task's artifacts as baseline for new task."""
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
        milestone_id=None,
        artifacts=baseline_artifacts,
    )
    logger.info(
        "previous_artifacts_copied_to_task",
        task_id=str(task_id),
        count=len(baseline_artifacts),
    )


async def _save_task_artifacts(
    artifact_repo: ArtifactRepository,
    session_id: UUID,
    task_id: UUID,
    extraction_result: ExtractionResult,
    previous_snapshot: list[Artifact],
) -> list[dict[str, Any]]:
    """Save artifacts from task extraction result."""
    # On first execution, copy previous task's artifacts as baseline
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
            milestone_id=None,
            artifacts=artifacts_data,
        )

        logger.info(
            "artifacts_saved_for_task",
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
            "language": a.kind,
            "content": a.content,
            "path": a.path,
        }
        for a in all_task_artifacts
    ]


def _prepare_worker_prompt(
    state: AgentState,
    task: dict[str, Any],
) -> str:
    """Prepare prompt for Worker execution from project plan task."""
    base_prompt = task.get("description", "")
    original_request = state.get("original_request", "")
    acceptance_criteria = task.get("acceptance_criteria", "")

    prompt_parts = []

    if original_request and original_request not in base_prompt:
        prompt_parts.append(f"Original user request:\n{original_request}")

    prompt_parts.append(f"Current task:\n{base_prompt}")

    if acceptance_criteria:
        prompt_parts.append(f"Acceptance criteria:\n{acceptance_criteria}")

    return "\n\n".join(prompt_parts)


def _get_complexity_from_task(task: dict[str, Any]) -> TaskComplexity:
    """Extract complexity from task dict."""
    complexity_str = task.get("complexity", "MODERATE")
    try:
        return TaskComplexity[complexity_str]
    except KeyError:
        return TaskComplexity.MODERATE


def _get_task_index(tasks: list[dict[str, Any]], task_id: str) -> int:
    """Get index of task in list."""
    for i, task in enumerate(tasks):
        if task.get("id") == task_id:
            return i
    return 0


async def execute_worker_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Execute task via Worker agent.

    Handles both fresh execution and retry scenarios,
    passing QA feedback for retries.

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
        project_plan = state.get("project_plan")
        if not project_plan:
            return {"error": "No project_plan available", "error_node": "execute_worker"}

        current_task_id = state.get("current_task_id")
        tasks = get_tasks_from_plan(project_plan)
        task = get_task_by_id(tasks, current_task_id) if current_task_id else None

        if task is None:
            return {
                "error": "No task available in project plan",
                "error_node": "execute_worker",
            }

        task_complexity = _get_complexity_from_task(task)
        task_idx = _get_task_index(tasks, current_task_id) if current_task_id else 0
        retry_count = state.get("retry_count", 0)

        logger.debug(
            "execute_worker_context",
            user_id=state["user_id"],
            session_id=str(state["session_id"]),
            task_id=str(state["task_id"]),
            current_task_id=current_task_id,
        )

        # Emit worker started event
        message = (
            "Executing task" if retry_count == 0 else f"Retrying task (attempt {retry_count + 1})"
        )
        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_STARTED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=state["task_id"],
                sequence_number=task_idx + 1,
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
        prompt = _prepare_worker_prompt(state, task)
        previous_output = task.get("worker_output")
        qa_feedback = state.get("current_qa_feedback")

        if retry_count > 0 and previous_output and qa_feedback:
            response = await worker.retry_with_feedback(
                milestone_id=state["task_id"],
                original_prompt=prompt,
                previous_output=previous_output,
                qa_feedback=qa_feedback,
                complexity=task_complexity,
                user_id=state["user_id"],
                session_id=state["session_id"],
                task_id=state["task_id"],
            )
        else:
            response = await worker.execute_milestone(
                milestone_id=state["task_id"],
                prompt=prompt,
                complexity=task_complexity,
                user_id=state["user_id"],
                session_id=state["session_id"],
                task_id=state["task_id"],
                preferred_model=None,
                context_messages=context_messages,
            )

        # Update project_plan task status
        if current_task_id:
            updated_plan_data = update_task_status(
                project_plan.plan_data,
                current_task_id,
                "in_progress",
            )
            # Store worker output in task
            for t in updated_plan_data.get("tasks", []):
                if t.get("id") == current_task_id:
                    t["worker_output"] = response.content
                    break
            project_plan.plan_data = updated_plan_data

        # Update context with new exchange
        context_messages = list(state.get("context_messages", []))
        context_messages.append(ChatMessage(role="user", content=prompt))
        context_messages.append(ChatMessage(role="assistant", content=response.content))

        # Calculate tokens and cost
        current_tokens = state.get("current_context_tokens", 0) + response.usage.total_tokens
        total_input = state.get("total_input_tokens", 0) + response.usage.input_tokens
        total_output = state.get("total_output_tokens", 0) + response.usage.output_tokens

        model = container.router.select_model(complexity=task_complexity)
        call_cost = container.router.calculate_cost(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        total_cost = Decimal(state.get("total_cost_usd", "0")) + call_cost

        logger.info(
            "worker_executed",
            task_index=task_idx,
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
                task_id=str(state["task_id"]),
                output_length=len(response.content),
                message="Worker response was cut off due to token limit",
            )
            return {
                "error": "Worker response was truncated due to token limit.",
                "error_node": "execute_worker",
                "current_output": response.content,
                "project_plan": project_plan,
            }

        # Persist plan data update
        plan_repo = ProjectPlanRepository(session)
        await plan_repo.update(project_plan.id, plan_data=project_plan.plan_data)
        await session.commit()

        # Extract and save artifacts
        extraction_result = extract_artifacts(response.content)

        if not extraction_result.artifacts and response.content.strip().startswith("{"):
            logger.warning(
                "artifact_extraction_empty",
                task_id=str(state["task_id"]),
                content_length=len(response.content),
                message="No artifacts extracted, JSON parsing may have failed",
            )

        artifacts_for_broadcast = await _save_task_artifacts(
            artifact_repo=artifact_repo,
            session_id=state["session_id"],
            task_id=state["task_id"],
            extraction_result=extraction_result,
            previous_snapshot=previous_snapshot,
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
                milestone_id=state["task_id"],
                sequence_number=task_idx + 1,
                agent="worker",
                status=AgentStatus.COMPLETED,
                message=f"Task executed ({response.usage.total_tokens} tokens)",
                details=worker_details,
            )
        )

        return {
            "current_output": response.content,
            "context_messages": context_messages,
            "current_context_tokens": current_tokens,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": str(total_cost),
            "project_plan": project_plan,
        }

    except Exception as e:
        logger.error("execute_worker_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "execute_worker",
        }


__all__ = [
    "execute_worker_node",
]
