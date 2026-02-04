"""Execution Breakpoint Node.

Checks if execution should pause after task completion
based on BreakpointConfig settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from agent.graph.state import AgentState
from agent.llm.schemas import BreakpointConfig
from agent.services.breakpoint_service import BreakpointService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def execution_breakpoint(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Check if execution should pause after current task.

    Called after verify_qa to determine if we should pause
    before proceeding to the next task.

    Args:
        state: Current graph state
        config: LangGraph RunnableConfig
        session: Database session (unused but required for consistency)

    Returns:
        Updated state with breakpoint info
    """
    # Session is passed for consistency with other nodes but not used
    _ = session
    # Get breakpoint config from state or config
    configurable = config.get("configurable", {})
    breakpoint_service: BreakpointService | None = configurable.get("breakpoint_service")

    # Get breakpoint config - first try from service, then from default
    if breakpoint_service:
        breakpoint_config = breakpoint_service.config
    else:
        breakpoint_config = BreakpointConfig()

    service = BreakpointService(breakpoint_config)

    # Get current task info
    current_task_id = _get_current_task_id(state)
    qa_result = state.get("current_qa_decision")
    task_status = "completed" if qa_result == "pass" else "failed"

    # Get plan data
    project_plan = state.get("project_plan")
    if project_plan and hasattr(project_plan, "plan_data"):
        plan_data = project_plan.plan_data
    else:
        plan_data = {"tasks": state.get("milestones", [])}

    # Check if should pause
    should_pause, reason = service.should_pause_after_task(
        task_id=current_task_id or "",
        task_status=task_status,
        plan_data=plan_data,
    )

    if should_pause:
        logger.info(
            "execution_breakpoint_pause",
            task_id=current_task_id,
            reason=reason,
        )

        # Get progress summary for the interrupt
        progress = get_current_progress(state)

        # Interrupt workflow and wait for user input
        user_response = interrupt(
            {
                "message": "Execution paused at breakpoint",
                "task_id": current_task_id,
                "reason": reason,
                "progress": progress,
            }
        )

        # Process user response (if they provide feedback or want to continue)
        return _process_user_response(state, user_response, reason)

    return {
        "waiting_for_execution_resume": False,
        "should_continue": True,
    }


def _get_current_task_id(state: AgentState) -> str | None:
    """Get current task ID from state.

    Args:
        state: Current workflow state

    Returns:
        Current task ID or None
    """
    # Try to get from project plan if available
    project_plan = state.get("project_plan")
    if project_plan and hasattr(project_plan, "plan_data"):
        plan_data = project_plan.plan_data
        tasks = plan_data.get("tasks", [])
        current_index = state.get("current_milestone_index", 0)
        if tasks and current_index < len(tasks):
            task_id = tasks[current_index].get("id")
            return str(task_id) if task_id is not None else None

    # Fall back to milestone-based tracking
    milestones = state.get("milestones", [])
    current_index = state.get("current_milestone_index", 0)
    if milestones and current_index < len(milestones):
        milestone = milestones[current_index]
        return str(milestone.get("id", ""))

    return None


def _process_user_response(
    state: AgentState,
    user_response: Any,
    reason: str | None,
) -> dict[str, Any]:
    """Process user response after breakpoint.

    Args:
        state: Current workflow state
        user_response: User's response from interrupt
        reason: Original pause reason

    Returns:
        State update based on user response
    """
    if user_response and isinstance(user_response, dict):
        action = user_response.get("action", "continue")

        if action == "abort":
            logger.info(
                "execution_breakpoint_aborted",
                task_id=str(state["task_id"]),
            )
            return {
                "waiting_for_execution_resume": False,
                "should_continue": False,
                "workflow_complete": True,
                "error": "Execution aborted by user at breakpoint",
                "error_node": "execution_breakpoint",
            }

        if action == "continue":
            logger.info(
                "execution_breakpoint_continued",
                task_id=str(state["task_id"]),
            )
            return {
                "waiting_for_execution_resume": False,
                "should_continue": True,
            }

    # Default: continue
    logger.info(
        "execution_breakpoint_default_continue",
        task_id=str(state["task_id"]),
    )
    return {
        "waiting_for_execution_resume": False,
        "should_continue": True,
    }


def execution_breakpoint_router(
    state: AgentState,
) -> Literal["advance", "__end__"]:
    """Route based on breakpoint decision.

    Returns:
        - "advance": Continue to next task
        - "__end__": Pause execution (will be resumed by API)
    """
    should_continue = state.get("should_continue", True)
    workflow_complete = state.get("workflow_complete", False)

    if workflow_complete or not should_continue:
        return "__end__"

    return "advance"


async def resume_execution(
    state: AgentState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Resume execution after breakpoint.

    Called when user continues execution via API.

    Args:
        state: Current workflow state
        config: LangGraph RunnableConfig

    Returns:
        State update for resuming execution
    """
    # config is available for future use (e.g., accessing container or event_bus)
    _ = config

    current_task_id = _get_current_task_id(state)

    logger.info(
        "execution_resumed",
        task_id=current_task_id,
        session_id=str(state.get("session_id")),
    )

    return {
        "waiting_for_execution_resume": False,
        "should_continue": True,
    }


def get_current_progress(state: AgentState) -> dict[str, Any]:
    """Get current execution progress for frontend.

    Returns summary of completed work and what's next.

    Args:
        state: Current workflow state

    Returns:
        Progress summary dict
    """
    project_plan = state.get("project_plan")
    if not project_plan:
        # Fall back to milestone-based progress
        return _get_milestone_progress(state)

    # Handle ProjectPlan object
    if hasattr(project_plan, "plan_data"):
        plan_data = project_plan.plan_data
    else:
        return {"error": "No plan data found"}

    tasks = plan_data.get("tasks", [])
    completed = [t for t in tasks if t.get("status") == "completed"]
    pending = [t for t in tasks if t.get("status") == "pending"]
    in_progress = [t for t in tasks if t.get("status") == "in_progress"]
    failed = [t for t in tasks if t.get("status") == "failed"]

    # Calculate feature/epic progress if applicable
    features = plan_data.get("features", [])
    epics = plan_data.get("epics", [])

    feature_progress = _calculate_feature_progress(tasks, features)
    epic_progress = _calculate_epic_progress(tasks, epics)

    current_task_id = _get_current_task_id(state)

    return {
        "total_tasks": len(tasks),
        "completed_tasks": len(completed),
        "pending_tasks": len(pending),
        "in_progress_tasks": len(in_progress),
        "failed_tasks": len(failed),
        "overall_percent": (len(completed) / len(tasks) * 100) if tasks else 0,
        "current_task": current_task_id,
        "breakpoint_reason": state.get("breakpoint_reason"),
        "feature_progress": feature_progress,
        "epic_progress": epic_progress,
    }


def _get_milestone_progress(state: AgentState) -> dict[str, Any]:
    """Get progress from milestone-based tracking.

    Args:
        state: Current workflow state

    Returns:
        Milestone-based progress summary
    """
    milestones = state.get("milestones", [])
    current_index = state.get("current_milestone_index", 0)

    completed = [m for m in milestones if m.get("status") == "completed"]
    failed = [m for m in milestones if m.get("status") == "failed"]

    return {
        "total_tasks": len(milestones),
        "completed_tasks": len(completed),
        "pending_tasks": len(milestones) - len(completed) - len(failed),
        "in_progress_tasks": 1 if current_index < len(milestones) else 0,
        "failed_tasks": len(failed),
        "overall_percent": (len(completed) / len(milestones) * 100) if milestones else 0,
        "current_task": (
            str(milestones[current_index]["id"]) if current_index < len(milestones) else None
        ),
        "breakpoint_reason": state.get("breakpoint_reason"),
        "feature_progress": [],
        "epic_progress": [],
    }


def _calculate_feature_progress(
    tasks: list[dict[str, Any]],
    features: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Calculate progress for each feature.

    Args:
        tasks: List of all tasks
        features: List of features

    Returns:
        List of feature progress dicts
    """
    if not features:
        return []

    feature_progress = []
    for feature in features:
        feature_id = feature.get("id")
        feature_tasks = [t for t in tasks if t.get("parent_feature_id") == feature_id]
        completed_count = len([t for t in feature_tasks if t.get("status") == "completed"])
        total_count = len(feature_tasks)

        feature_progress.append(
            {
                "id": feature_id,
                "title": feature.get("title", feature_id),
                "completed": completed_count,
                "total": total_count,
                "percent": (completed_count / total_count * 100) if total_count > 0 else 0,
            }
        )

    return feature_progress


def _calculate_epic_progress(
    tasks: list[dict[str, Any]],
    epics: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Calculate progress for each epic.

    Args:
        tasks: List of all tasks
        epics: List of epics

    Returns:
        List of epic progress dicts
    """
    if not epics:
        return []

    epic_progress = []
    for epic in epics:
        epic_id = epic.get("id")
        epic_tasks = [t for t in tasks if t.get("parent_epic_id") == epic_id]
        completed_count = len([t for t in epic_tasks if t.get("status") == "completed"])
        total_count = len(epic_tasks)

        epic_progress.append(
            {
                "id": epic_id,
                "title": epic.get("title", epic_id),
                "completed": completed_count,
                "total": total_count,
                "percent": (completed_count / total_count * 100) if total_count > 0 else 0,
            }
        )

    return epic_progress
