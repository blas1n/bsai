"""Advance node for milestone progression."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import MilestoneStatus, TaskStatus
from agent.events import EventType, MilestoneRetryEvent, MilestoneStatusChangedEvent
from agent.memory import store_task_memory

from ..state import AgentState
from . import get_event_bus, get_memory_manager

logger = structlog.get_logger()


async def advance_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Advance to next milestone or complete workflow.

    Handles three scenarios:
    1. Retry - Increment retry count, stay on milestone
    2. Fail - Mark task as failed, complete workflow
    3. Pass - Move to next milestone or complete

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session (unused but required for signature)

    Returns:
        Partial state with updated index or completion flag
    """
    milestones = state.get("milestones")
    idx = state.get("current_milestone_index")
    qa_decision = state.get("current_qa_decision")
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

    if milestones is None or idx is None:
        return {"error": "No milestones available", "error_node": "advance"}

    milestone = milestones[idx] if idx < len(milestones) else None

    if qa_decision == "retry":
        # Increment retry count, stay on same milestone
        new_retry = state.get("retry_count", 0) + 1
        settings = get_agent_settings()
        max_retries = settings.max_milestone_retries

        # Check if max retries exceeded - if so, fail the milestone
        if new_retry >= max_retries:
            logger.warning(
                "milestone_max_retries_exceeded",
                milestone_index=idx,
                retry_count=new_retry,
                max_retries=max_retries,
            )

            # Emit milestone failed event due to max retries
            if milestone:
                await event_bus.emit(
                    MilestoneStatusChangedEvent(
                        type=EventType.MILESTONE_FAILED,
                        session_id=state["session_id"],
                        task_id=state["task_id"],
                        milestone_id=milestone["id"],
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
            "milestone_retry",
            milestone_index=idx,
            retry_count=new_retry,
            max_retries=max_retries,
        )

        # Emit milestone retry event
        if milestone:
            await event_bus.emit(
                MilestoneRetryEvent(
                    type=EventType.MILESTONE_RETRY,
                    session_id=state["session_id"],
                    task_id=state["task_id"],
                    milestone_id=milestone["id"],
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

    elif qa_decision == "fail":
        # Milestone failed, mark task as failed
        logger.warning(
            "milestone_failed",
            milestone_index=idx,
        )

        # Emit milestone failed event
        if milestone:
            await event_bus.emit(
                MilestoneStatusChangedEvent(
                    type=EventType.MILESTONE_FAILED,
                    session_id=state["session_id"],
                    task_id=state["task_id"],
                    milestone_id=milestone["id"],
                    sequence_number=idx + 1,
                    previous_status=MilestoneStatus.IN_PROGRESS,
                    new_status=MilestoneStatus.FAILED,
                    agent="advance",
                    message="Milestone failed QA validation",
                )
            )

        return {
            "task_status": TaskStatus.FAILED,
            "workflow_complete": True,
            "should_continue": False,
        }

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
