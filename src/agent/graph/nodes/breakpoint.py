"""Breakpoint node for Human-in-the-Loop workflow control.

This node allows pausing the workflow at critical points
to let users review the current state before proceeding.
"""

from __future__ import annotations

from typing import Any, cast

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from agent.db.models.enums import TaskStatus

from ..broadcast import broadcast_breakpoint_hit
from ..state import AgentState, MilestoneData
from . import check_task_cancelled, get_ws_manager

logger = structlog.get_logger()


async def qa_breakpoint_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Breakpoint before QA verification for human review.

    This node broadcasts a breakpoint notification and pauses
    the workflow so users can review the worker output before
    QA verification. Only pauses if breakpoints are enabled.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with optional user input
    """
    # Check if breakpoints are enabled - first from dynamic config (WebSocket), then from state
    ws_manager = get_ws_manager(config)
    task_id = state["task_id"]

    # Dynamic config (from WebSocket) takes precedence over initial state
    breakpoint_enabled = ws_manager.is_breakpoint_enabled(task_id)
    if not breakpoint_enabled:
        # Fall back to initial state if no dynamic config
        breakpoint_enabled = state.get("breakpoint_enabled", False)

    logger.info(
        "qa_breakpoint_node_entered",
        task_id=str(task_id),
        breakpoint_enabled=breakpoint_enabled,
    )

    # Skip breakpoint if not enabled
    if not breakpoint_enabled:
        logger.info(
            "qa_breakpoint_skipped",
            task_id=str(task_id),
            breakpoint_enabled=breakpoint_enabled,
        )
        return {}

    # Get current milestone index
    milestone_idx = state.get("current_milestone_index", 0)

    # Skip if already paused at this milestone (prevents re-triggering after resume)
    if ws_manager.is_paused_at(task_id, milestone_idx):
        logger.info(
            "qa_breakpoint_already_paused_at",
            task_id=str(task_id),
            milestone_index=milestone_idx,
        )
        return {}

    # Check if task was cancelled before breakpoint
    if await check_task_cancelled(session, state["task_id"]):
        logger.info("qa_breakpoint_cancelled", task_id=str(state["task_id"]))
        return {
            "error": "Task cancelled by user",
            "error_node": "qa_breakpoint",
            "task_status": TaskStatus.FAILED,
            "workflow_complete": True,
        }

    milestones = state.get("milestones", [])
    idx = state.get("current_milestone_index", 0)
    current_milestone = milestones[idx] if idx < len(milestones) else None

    # Get last worker output
    last_worker_output = None
    if current_milestone:
        last_worker_output = current_milestone.get("worker_output")

    # Convert milestones to serializable format for broadcast
    milestones_data = []
    for m in milestones:
        milestones_data.append(
            {
                "id": str(m["id"]),
                "description": m.get("description", ""),
                "status": str(m.get("status", "pending")),
                "worker_output": m.get("worker_output"),
                "qa_feedback": m.get("qa_feedback"),
            }
        )

    # Broadcast breakpoint hit notification
    await broadcast_breakpoint_hit(
        ws_manager=ws_manager,
        session_id=state["session_id"],
        task_id=state["task_id"],
        node_name="qa_breakpoint",
        agent_type="qa",
        current_milestone_index=idx,
        total_milestones=len(milestones),
        milestones=milestones_data,
        last_worker_output=last_worker_output,
    )

    logger.info(
        "qa_breakpoint_hit",
        task_id=str(state["task_id"]),
        milestone_index=idx,
    )

    # Record which milestone is paused (cleared on resume, not cleared on reject with feedback)
    ws_manager.set_paused_at(task_id, idx)

    # Interrupt workflow and wait for user input
    # User can either:
    # - Resume with no input (None) to continue as-is
    # - Provide modified input to override the worker output
    user_response = interrupt(
        {
            "message": "Review worker output before QA verification",
            "milestone_index": idx,
            "milestone_description": (
                current_milestone.get("description") if current_milestone else None
            ),
            "worker_output": last_worker_output,
        }
    )

    # Process user response
    if user_response and isinstance(user_response, dict):
        user_input = user_response.get("user_input")
        rejected = user_response.get("rejected", False)

        if rejected:
            if user_input:
                # Rejected WITH feedback -> Re-run worker with user feedback
                # This is like QA "fail" - we go back to worker with the feedback
                logger.info(
                    "qa_breakpoint_rejected_with_feedback",
                    task_id=str(state["task_id"]),
                    milestone_index=idx,
                    feedback=user_input[:100],  # Log first 100 chars
                )
                # Update milestone with QA-like feedback to trigger worker retry
                updated_milestones = list(milestones)
                updated_milestone = dict(current_milestone) if current_milestone else {}
                updated_milestone["qa_decision"] = "fail"
                updated_milestone["qa_feedback"] = user_input
                updated_milestone["status"] = "fail"
                updated_milestones[idx] = cast(MilestoneData, updated_milestone)
                return {
                    "milestones": updated_milestones,
                    "qa_decision": "fail",  # Signal to route back to worker
                    "breakpoint_user_input": user_input,
                }
            else:
                # Rejected WITHOUT feedback -> Cancel task
                logger.info(
                    "qa_breakpoint_rejected_cancelled",
                    task_id=str(state["task_id"]),
                )
                return {
                    "error": "Task cancelled by user",
                    "error_node": "qa_breakpoint",
                    "task_status": TaskStatus.FAILED,
                    "workflow_complete": True,
                    "user_cancelled": True,  # Flag to indicate user cancellation
                }

        if user_input:
            # User provided modified input - update the worker output
            logger.info(
                "qa_breakpoint_user_modified",
                task_id=str(state["task_id"]),
                milestone_index=idx,
            )
            # Update current milestone with user's modified output
            updated_milestones = list(milestones)
            updated_milestone = dict(current_milestone) if current_milestone else {}
            updated_milestone["worker_output"] = user_input
            updated_milestones[idx] = cast(MilestoneData, updated_milestone)
            return {
                "milestones": updated_milestones,
                "breakpoint_user_input": user_input,
            }

    logger.info(
        "qa_breakpoint_resumed",
        task_id=str(state["task_id"]),
    )

    # Continue as-is
    return {}
