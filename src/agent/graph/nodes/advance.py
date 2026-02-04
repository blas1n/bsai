"""Advance node for milestone/task progression.

Supports both:
1. New flow: project_plan with tasks
2. Legacy flow: milestones list
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
    find_next_pending_task,
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
    """Advance to next task/milestone or complete workflow.

    Handles three scenarios:
    1. Retry - Increment retry count, stay on current task
    2. Fail - Mark task as failed, complete workflow
    3. Pass - Move to next task or complete

    Supports both:
    - New flow: project_plan with tasks (dependency-aware)
    - Legacy flow: milestones list (sequential)

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with updated index or completion flag
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

    # Check if using new project_plan flow or legacy milestones flow
    project_plan = state.get("project_plan")

    if project_plan:
        return await _advance_with_project_plan(
            state=state,
            config=config,
            session=session,
            project_plan=project_plan,
            event_bus=event_bus,
        )
    else:
        return await _advance_with_milestones(
            state=state,
            config=config,
            session=session,
            event_bus=event_bus,
        )


async def _advance_with_project_plan(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
    project_plan: ProjectPlan,
    event_bus: Any,
) -> dict[str, Any]:
    """Advance using project_plan-based task flow.

    Uses dependency-aware task selection.

    Args:
        state: Current workflow state
        config: LangGraph config
        session: Database session
        project_plan: Current project plan
        event_bus: Event bus for emitting events

    Returns:
        Partial state with updated task or completion flag
    """
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

        # Find next pending task (dependency-aware)
        updated_tasks = get_tasks_from_plan(project_plan)
        next_task = find_next_pending_task(updated_tasks)

        if next_task is None:
            # All tasks completed
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
                milestones=state.get("milestones", []),
            )

            return {
                "project_plan": project_plan,
                "task_status": TaskStatus.COMPLETED,
                "workflow_complete": True,
                "should_continue": False,
            }

        # Advance to next task
        next_task_id = next_task["id"]
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


async def _advance_with_milestones(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
    event_bus: Any,
) -> dict[str, Any]:
    """Legacy advance using milestones list.

    Sequential milestone progression.

    Args:
        state: Current workflow state
        config: LangGraph config
        session: Database session
        event_bus: Event bus for emitting events

    Returns:
        Partial state with updated index or completion flag
    """
    milestones = state.get("milestones")
    idx = state.get("current_milestone_index")
    qa_decision = state.get("current_qa_decision")

    if milestones is None or idx is None:
        return {"error": "No milestones available", "error_node": "advance"}

    milestone = milestones[idx] if idx < len(milestones) else None
    milestone_id = milestone["id"] if milestone else state["task_id"]

    if qa_decision == "retry":
        return await _handle_retry(
            state=state,
            event_bus=event_bus,
            milestone_id=milestone_id,
            idx=idx,
        )

    elif qa_decision == "fail":
        return await _handle_fail(
            state=state,
            event_bus=event_bus,
            milestone_id=milestone_id,
            idx=idx,
        )

    else:  # pass
        # Emit milestone passed event
        if milestone:
            await event_bus.emit(
                MilestoneStatusChangedEvent(
                    type=EventType.MILESTONE_COMPLETED,
                    session_id=state["session_id"],
                    task_id=state["task_id"],
                    milestone_id=milestone["id"],
                    sequence_number=idx + 1,
                    previous_status=MilestoneStatus.IN_PROGRESS,
                    new_status=MilestoneStatus.PASSED,
                    agent="advance",
                    message="Milestone passed QA validation",
                )
            )

        # Move to next milestone
        next_idx = idx + 1

        if next_idx >= len(milestones):
            # All milestones complete
            logger.info(
                "workflow_complete",
                task_id=str(state["task_id"]),
                milestone_count=len(milestones),
            )

            # Store completed task to long-term memory using DI container
            memory_manager = get_memory_manager(config, session)
            await store_task_memory(
                manager=memory_manager,
                user_id=state["user_id"],
                session_id=state["session_id"],
                task_id=state["task_id"],
                original_request=state["original_request"],
                final_response=state.get("final_response") or "",
                milestones=state.get("milestones", []),
            )

            return {
                "task_status": TaskStatus.COMPLETED,
                "workflow_complete": True,
                "should_continue": False,
            }

        # Advance to next milestone
        logger.info(
            "milestone_advanced",
            from_index=idx,
            to_index=next_idx,
        )

        return {
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
    """Handle retry scenario for both flows.

    Args:
        state: Current workflow state
        event_bus: Event bus for emitting events
        milestone_id: Milestone/task ID for events
        idx: Current index
        task_id: Optional task ID for project_plan flow

    Returns:
        Partial state for retry
    """
    new_retry = state.get("retry_count", 0) + 1
    settings = get_agent_settings()
    max_retries = settings.max_milestone_retries

    # Check if max retries exceeded - if so, fail the milestone
    if new_retry >= max_retries:
        logger.warning(
            "task_max_retries_exceeded",
            task_id=task_id,
            milestone_index=idx,
            retry_count=new_retry,
            max_retries=max_retries,
        )

        # Emit milestone failed event due to max retries
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

    # Emit milestone retry event
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
    """Handle fail scenario for both flows.

    Args:
        state: Current workflow state
        event_bus: Event bus for emitting events
        milestone_id: Milestone/task ID for events
        idx: Current index
        task_id: Optional task ID for project_plan flow

    Returns:
        Partial state for failure
    """
    logger.warning(
        "task_failed",
        task_id=task_id,
        milestone_index=idx,
    )

    # Emit milestone failed event
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
