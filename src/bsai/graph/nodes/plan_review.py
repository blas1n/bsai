"""Plan Review Breakpoint Node.

This node implements the Human-in-the-Loop pattern for plan review.
It pauses workflow execution until the user approves, revises, or rejects the plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from bsai.db.models.enums import TaskStatus
from bsai.events import BreakpointHitEvent, EventType
from bsai.graph.state import AgentState
from bsai.llm.schemas import PlanStatus

from . import NodeContext, check_task_cancelled

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def plan_review_breakpoint(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Breakpoint for plan review.

    This node checks if the plan requires user review and pauses
    execution if configured to do so. It implements the Human-in-the-Loop
    pattern for project plan approval.

    The workflow will resume when:
    1. User approves the plan -> continues to execution
    2. User revises the plan -> returns to architect for revision
    3. User rejects the plan -> ends workflow

    Args:
        state: Current workflow state
        config: LangGraph config with dependencies
        session: Database session

    Returns:
        Updated state with breakpoint info
    """
    ctx = NodeContext.from_config(config, session)
    task_id = state["task_id"]
    session_id = state["session_id"]

    # Check if task was cancelled before breakpoint
    if await check_task_cancelled(session, task_id):
        logger.info("plan_review_cancelled", task_id=str(task_id))
        return ctx.cancelled_response("plan_review")

    project_plan = state.get("project_plan")
    plan_status = state.get("plan_status")

    # Check if we have a plan to review
    if not project_plan:
        logger.warning("plan_review_no_plan", task_id=str(task_id))
        return {"should_continue": True}

    plan_id = project_plan.id if hasattr(project_plan, "id") else None

    # If plan is already approved, continue
    if plan_status == PlanStatus.APPROVED:
        logger.info(
            "plan_review_already_approved",
            task_id=str(task_id),
            plan_id=str(plan_id) if plan_id else None,
        )
        return {"should_continue": True, "plan_status": PlanStatus.APPROVED}

    # If plan is rejected, end workflow
    if plan_status == PlanStatus.REJECTED:
        logger.info(
            "plan_review_rejected",
            task_id=str(task_id),
            plan_id=str(plan_id) if plan_id else None,
        )
        return {
            "should_continue": False,
            "plan_status": PlanStatus.REJECTED,
            "workflow_complete": True,
        }

    # Check breakpoint configuration
    breakpoint_enabled = state.get("breakpoint_enabled", False)

    # Also check breakpoint service for dynamic config
    if ctx.breakpoint_service:
        dynamic_enabled = ctx.breakpoint_service.is_breakpoint_enabled(task_id)
        if dynamic_enabled:
            breakpoint_enabled = True

    # If breakpoint is disabled, auto-approve
    if not breakpoint_enabled:
        logger.info(
            "plan_review_auto_approved",
            task_id=str(task_id),
            plan_id=str(plan_id) if plan_id else None,
        )
        return {"should_continue": True, "plan_status": PlanStatus.APPROVED}

    # Extract plan data for the breakpoint event
    plan_data = _extract_plan_data(project_plan)

    # Emit breakpoint hit event
    await ctx.event_bus.emit(
        BreakpointHitEvent(
            type=EventType.BREAKPOINT_HIT,
            session_id=session_id,
            task_id=task_id,
            node_name="plan_review",
            agent_type="architect",
            current_milestone_index=0,
            total_milestones=plan_data.get("total_tasks", 0),
            milestones=[],  # Plan review doesn't have milestones yet
            last_worker_output=None,
            last_qa_result=None,
        )
    )

    logger.info(
        "plan_review_waiting",
        task_id=str(task_id),
        plan_id=str(plan_id) if plan_id else None,
        total_tasks=plan_data.get("total_tasks", 0),
    )

    # Interrupt workflow and wait for user input
    # User can:
    # - Approve with no input (None) to continue
    # - Provide revision feedback to modify the plan
    # - Reject to end the workflow
    user_response = interrupt(
        {
            "message": "Review project plan before execution",
            "plan_id": str(plan_id) if plan_id else None,
            "plan_title": plan_data.get("title"),
            "plan_overview": plan_data.get("overview"),
            "total_tasks": plan_data.get("total_tasks"),
            "structure_type": plan_data.get("structure_type"),
        }
    )

    # Process user response
    return _process_user_response(state, user_response, plan_id)


def _extract_plan_data(project_plan: Any) -> dict[str, Any]:
    """Extract plan data from ProjectPlan object.

    Args:
        project_plan: ProjectPlan instance or dict

    Returns:
        Dictionary with plan data
    """
    if hasattr(project_plan, "title"):
        return {
            "title": project_plan.title,
            "overview": getattr(project_plan, "overview", None),
            "total_tasks": getattr(project_plan, "total_tasks", 0),
            "structure_type": getattr(project_plan, "structure_type", None),
        }
    elif isinstance(project_plan, dict):
        return {
            "title": project_plan.get("title"),
            "overview": project_plan.get("overview"),
            "total_tasks": project_plan.get("total_tasks", 0),
            "structure_type": project_plan.get("structure_type"),
        }
    return {}


def _process_user_response(
    state: AgentState,
    user_response: Any,
    plan_id: Any,
) -> dict[str, Any]:
    """Process user response after breakpoint.

    Args:
        state: Current workflow state
        user_response: User's response from interrupt
        plan_id: Plan UUID

    Returns:
        State update based on user response
    """
    if user_response and isinstance(user_response, dict):
        action = user_response.get("action", "approve")
        feedback = user_response.get("feedback")

        if action == "reject":
            logger.info(
                "plan_review_user_rejected",
                task_id=str(state["task_id"]),
                plan_id=str(plan_id) if plan_id else None,
            )
            return {
                "should_continue": False,
                "plan_status": PlanStatus.REJECTED,
                "workflow_complete": True,
                "error": "Plan rejected by user",
                "error_node": "plan_review",
                "task_status": TaskStatus.FAILED,
            }

        if action == "revise" and feedback:
            logger.info(
                "plan_review_revision_requested",
                task_id=str(state["task_id"]),
                plan_id=str(plan_id) if plan_id else None,
                feedback_length=len(feedback),
            )
            return {
                "waiting_for_plan_review": False,
                "revision_requested": True,
                "revision_feedback": feedback,
                "plan_status": PlanStatus.DRAFT,
            }

    # Default: approve
    logger.info(
        "plan_review_user_approved",
        task_id=str(state["task_id"]),
        plan_id=str(plan_id) if plan_id else None,
    )
    return {
        "waiting_for_plan_review": False,
        "should_continue": True,
        "plan_status": PlanStatus.APPROVED,
    }


def plan_review_router(
    state: AgentState,
) -> Literal["execute_worker", "architect", "__end__"]:
    """Route based on plan review result.

    Determines the next node based on the plan status after
    user review.

    Args:
        state: Current workflow state

    Returns:
        Next node based on plan status:
        - "execute_worker": Plan approved, continue to execution
        - "architect": Plan needs revision
        - "__end__": Plan rejected or workflow should end
    """
    plan_status = state.get("plan_status")
    revision_requested = state.get("revision_requested", False)
    workflow_complete = state.get("workflow_complete", False)

    # If workflow is marked complete, end
    if workflow_complete:
        return "__end__"

    # If revision requested, go back to architect
    if revision_requested:
        logger.info(
            "plan_review_routing_to_architect",
            task_id=str(state["task_id"]),
        )
        return "architect"

    # If approved, continue to worker
    if plan_status == PlanStatus.APPROVED:
        logger.info(
            "plan_review_routing_to_worker",
            task_id=str(state["task_id"]),
        )
        return "execute_worker"

    # If rejected, end
    if plan_status == PlanStatus.REJECTED:
        return "__end__"

    # Default: end (safety fallback)
    logger.warning(
        "plan_review_router_unknown_state",
        task_id=str(state["task_id"]),
        plan_status=str(plan_status) if plan_status else None,
    )
    return "__end__"


async def resume_after_approval(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Resume workflow after plan approval.

    Called when user approves the plan via API.
    This function updates the state to continue execution.

    Args:
        state: Current workflow state
        config: LangGraph config
        session: Database session

    Returns:
        State update for resuming after approval
    """
    project_plan = state.get("project_plan")
    plan_id = project_plan.id if project_plan and hasattr(project_plan, "id") else None

    logger.info(
        "plan_review_resumed_after_approval",
        task_id=str(state["task_id"]),
        plan_id=str(plan_id) if plan_id else None,
    )

    return {
        "waiting_for_plan_review": False,
        "should_continue": True,
        "plan_status": PlanStatus.APPROVED,
    }


async def resume_after_revision(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
    feedback: str,
) -> dict[str, Any]:
    """Resume workflow after plan revision request.

    Called when user requests revision via API.
    The Architect will regenerate the plan based on user feedback.

    Args:
        state: Current workflow state
        config: LangGraph config
        session: Database session
        feedback: User's revision feedback

    Returns:
        State update for resuming with revision request
    """
    project_plan = state.get("project_plan")
    plan_id = project_plan.id if project_plan and hasattr(project_plan, "id") else None

    logger.info(
        "plan_review_resumed_for_revision",
        task_id=str(state["task_id"]),
        plan_id=str(plan_id) if plan_id else None,
        feedback_length=len(feedback),
    )

    return {
        "waiting_for_plan_review": False,
        "revision_requested": True,
        "revision_feedback": feedback,
        "plan_status": PlanStatus.DRAFT,
    }


async def resume_after_rejection(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
    reason: str | None = None,
) -> dict[str, Any]:
    """Resume workflow after plan rejection.

    Called when user rejects the plan via API.
    The workflow will end.

    Args:
        state: Current workflow state
        config: LangGraph config
        session: Database session
        reason: Optional rejection reason

    Returns:
        State update for ending workflow after rejection
    """
    project_plan = state.get("project_plan")
    plan_id = project_plan.id if project_plan and hasattr(project_plan, "id") else None

    logger.info(
        "plan_review_resumed_after_rejection",
        task_id=str(state["task_id"]),
        plan_id=str(plan_id) if plan_id else None,
        reason=reason,
    )

    return {
        "waiting_for_plan_review": False,
        "should_continue": False,
        "plan_status": PlanStatus.REJECTED,
        "workflow_complete": True,
        "error": f"Plan rejected by user: {reason}" if reason else "Plan rejected by user",
        "error_node": "plan_review",
        "task_status": TaskStatus.FAILED,
    }
