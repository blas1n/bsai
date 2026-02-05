"""Advance node for task progression.

Handles sequential task execution with simple next-task selection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import MilestoneStatus, TaskStatus
from agent.db.repository.project_plan_repo import ProjectPlanRepository
from agent.events import EventType, MilestoneRetryEvent, MilestoneStatusChangedEvent
from agent.graph.utils import (
    get_task_index,
    get_tasks_from_plan,
    update_task_status,
)
from agent.memory import store_task_memory

from ..state import AgentState
from . import get_event_bus, get_memory_manager

if TYPE_CHECKING:
    from agent.db.models.project_plan import ProjectPlan

logger = structlog.get_logger()


async def advance_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Advance to next task or complete workflow.

    Handles three scenarios:
    1. Retry - Increment retry count, stay on current task
    2. Fail - Mark task as failed, complete workflow
    3. Pass - Move to next task or complete

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with updated task info
    """
    event_bus = get_event_bus(config)

    # If workflow is already complete (e.g., cancelled or error), just finalize
    if state.get("workflow_complete") or state.get("error"):
        logger.info(
            "advance_early_termination",
            workflow_complete=state.get("workflow_complete"),
            error=state.get("error"),
        )
        return {
            "task_status": TaskStatus.FAILED,
            "workflow_complete": True,
            "should_continue": False,
        }

    project_plan = state.get("project_plan")
    if not project_plan:
        return {
            "error": "No project plan available",
            "error_node": "advance",
            "workflow_complete": True,
        }

    qa_decision = state.get("current_qa_decision")
    current_task_id: str | None = state.get("current_task_id")  # type: ignore[assignment]
    idx = state.get("current_milestone_index", 0)

    # Use task_id as fallback for milestone_id in events
    milestone_id = state["task_id"]

    if qa_decision == "retry":
        return await _handle_retry(
            state=state,
            event_bus=event_bus,
            milestone_id=milestone_id,
            idx=idx,
            task_id=current_task_id,
        )

    elif qa_decision == "fail":
        return await _handle_fail(
            state=state,
            event_bus=event_bus,
            milestone_id=milestone_id,
            idx=idx,
            task_id=current_task_id,
        )

    else:  # pass
        return await _handle_pass(
            state=state,
            config=config,
            session=session,
            project_plan=project_plan,
            event_bus=event_bus,
            current_task_id=current_task_id,
            idx=idx,
            milestone_id=milestone_id,
        )


def _get_next_pending_task(tasks: list[dict[str, Any]]) -> str | None:
    """Find next pending task in sequential order.

    Args:
        tasks: List of task dictionaries from plan_data

    Returns:
        Task ID of next pending task, or None if all complete
    """
    for task in tasks:
        if task.get("status", "pending") == "pending":
            return task["id"]
    return None


def _is_all_completed(tasks: list[dict[str, Any]]) -> bool:
    """Check if all tasks are completed or failed.

    Args:
        tasks: List of task dictionaries

    Returns:
        True if no pending or in_progress tasks remain
    """
    for task in tasks:
        status = task.get("status", "pending")
        if status in ("pending", "in_progress"):
            return False
    return True


async def _handle_pass(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
    project_plan: ProjectPlan,
    event_bus: Any,
    current_task_id: str | None,
    idx: int,
    milestone_id: Any,
) -> dict[str, Any]:
    """Handle pass scenario - mark task complete and advance.

    Args:
        state: Current workflow state
        config: LangGraph config
        session: Database session
        project_plan: Current project plan
        event_bus: Event bus for emitting events
        current_task_id: Current task ID
        idx: Current index
        milestone_id: Milestone ID for events

    Returns:
        Partial state with updated task info
    """
    # Mark current task as completed
    if current_task_id:
        updated_plan_data = update_task_status(
            project_plan.plan_data,
            current_task_id,
            "completed",
        )

        # Persist to database
        plan_repo = ProjectPlanRepository(session)
        await plan_repo.update(
            project_plan.id,
            plan_data=updated_plan_data,
            completed_tasks=project_plan.completed_tasks + 1,
        )
        await session.commit()

        # Update project_plan reference
        project_plan.plan_data = updated_plan_data
        project_plan.completed_tasks += 1

        # Emit task completed event
        await event_bus.emit(
            MilestoneStatusChangedEvent(
                type=EventType.MILESTONE_COMPLETED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=milestone_id,
                sequence_number=idx + 1,
                previous_status=MilestoneStatus.IN_PROGRESS,
                new_status=MilestoneStatus.PASSED,
                agent="advance",
                message=f"Task {current_task_id} passed QA validation",
            )
        )

    # Get updated tasks list
    updated_tasks = get_tasks_from_plan(project_plan)

    # Check if all tasks completed
    if _is_all_completed(updated_tasks):
        logger.info(
            "workflow_complete",
            task_id=str(state["task_id"]),
            total_tasks=len(updated_tasks),
            completed_tasks=project_plan.completed_tasks,
        )

        # Update plan status
        plan_repo = ProjectPlanRepository(session)
        await plan_repo.update(project_plan.id, status="completed")
        await session.commit()

        # Store completed task to long-term memory
        memory_manager = get_memory_manager(config, session)
        await store_task_memory(
            manager=memory_manager,
            user_id=state["user_id"],
            session_id=state["session_id"],
            task_id=state["task_id"],
            original_request=state["original_request"],
            final_response=state.get("final_response") or "",
            milestones=[],
        )

        return {
            "project_plan": project_plan,
            "task_status": TaskStatus.COMPLETED,
            "workflow_complete": True,
            "should_continue": False,
        }

    # Find next pending task
    next_task_id = _get_next_pending_task(updated_tasks)

    if not next_task_id:
        # No more pending tasks
        logger.info(
            "workflow_complete_no_pending",
            task_id=str(state["task_id"]),
        )
        return {
            "project_plan": project_plan,
            "task_status": TaskStatus.COMPLETED,
            "workflow_complete": True,
            "should_continue": False,
        }

    next_idx = get_task_index(updated_tasks, next_task_id)

    logger.info(
        "task_advanced",
        from_task=current_task_id,
        to_task=next_task_id,
        to_index=next_idx,
    )

    return {
        "project_plan": project_plan,
        "current_task_id": next_task_id,
        "current_milestone_index": next_idx,
        "retry_count": 0,
        "current_prompt": None,
        "current_output": None,
        "current_qa_decision": None,
        "current_qa_feedback": None,
        "should_continue": True,
    }


async def _handle_retry(
    state: AgentState,
    event_bus: Any,
    milestone_id: Any,
    idx: int,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Handle retry scenario.

    Args:
        state: Current workflow state
        event_bus: Event bus for emitting events
        milestone_id: Milestone/task ID for events
        idx: Current index
        task_id: Task ID for logging

    Returns:
        Partial state for retry
    """
    new_retry = state.get("retry_count", 0) + 1
    settings = get_agent_settings()
    max_retries = settings.max_milestone_retries

    # Check if max retries exceeded - if so, fail the task
    if new_retry >= max_retries:
        logger.warning(
            "task_max_retries_exceeded",
            task_id=task_id,
            milestone_index=idx,
            retry_count=new_retry,
            max_retries=max_retries,
        )

        # Emit task failed event due to max retries
        await event_bus.emit(
            MilestoneStatusChangedEvent(
                type=EventType.MILESTONE_FAILED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=milestone_id,
                sequence_number=idx + 1,
                previous_status=MilestoneStatus.IN_PROGRESS,
                new_status=MilestoneStatus.FAILED,
                agent="advance",
                message="Failed after maximum retries",
            )
        )

        return {
            "retry_count": new_retry,
            "current_qa_decision": "fail",  # Override to fail
            "task_status": TaskStatus.FAILED,
            "workflow_complete": True,
            "should_continue": False,
        }

    logger.info(
        "task_retry",
        task_id=task_id,
        milestone_index=idx,
        retry_count=new_retry,
        max_retries=max_retries,
    )

    # Emit task retry event
    await event_bus.emit(
        MilestoneRetryEvent(
            type=EventType.MILESTONE_RETRY,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone_id,
            sequence_number=idx + 1,
            retry_count=new_retry,
            max_retries=max_retries,
            feedback=state.get("current_qa_feedback"),
        )
    )

    return {
        "retry_count": new_retry,
        "current_qa_decision": None,
        # Keep current_qa_feedback for Worker to use in retry
        "should_continue": False,  # Signal to go back to worker
    }


async def _handle_fail(
    state: AgentState,
    event_bus: Any,
    milestone_id: Any,
    idx: int,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Handle fail scenario.

    Args:
        state: Current workflow state
        event_bus: Event bus for emitting events
        milestone_id: Milestone/task ID for events
        idx: Current index
        task_id: Task ID for logging

    Returns:
        Partial state for failure
    """
    logger.warning(
        "task_failed",
        task_id=task_id,
        milestone_index=idx,
    )

    # Emit task failed event
    await event_bus.emit(
        MilestoneStatusChangedEvent(
            type=EventType.MILESTONE_FAILED,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone_id,
            sequence_number=idx + 1,
            previous_status=MilestoneStatus.IN_PROGRESS,
            new_status=MilestoneStatus.FAILED,
            agent="advance",
            message="Task failed QA validation",
        )
    )

    return {
        "task_status": TaskStatus.FAILED,
        "workflow_complete": True,
        "should_continue": False,
    }
