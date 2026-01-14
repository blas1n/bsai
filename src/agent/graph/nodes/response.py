"""Response generation node."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ResponderAgent
from agent.events import AgentActivityEvent, AgentStatus, EventType

from ..state import AgentState
from . import get_container, get_event_bus

logger = structlog.get_logger()


async def generate_response_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Generate final user-facing response via Responder agent.

    Called after all milestones are complete to create a clean,
    localized response for the user.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with final_response
    """
    container = get_container(config)
    event_bus = get_event_bus(config)

    # If there was an error or cancellation, return the error message as final response
    if state.get("error"):
        error_msg = state.get("error", "Task failed or was cancelled")
        logger.info(
            "response_skipped_due_to_error",
            task_id=str(state["task_id"]),
            error=error_msg,
        )
        return {
            "final_response": f"Task could not be completed: {error_msg}",
        }

    try:
        # Emit responder started event
        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_STARTED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=state["task_id"],  # Use task_id as placeholder
                sequence_number=0,
                agent="responder",
                status=AgentStatus.STARTED,
                message="Generating final response",
            )
        )

        responder = ResponderAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
        )

        # Get worker output from last milestone
        milestones = state.get("milestones", [])
        worker_output = ""
        if milestones:
            last_milestone = milestones[-1]
            worker_output = last_milestone.get("worker_output") or ""

        # Check if artifacts were generated
        has_artifacts = bool(worker_output and "```" in worker_output)

        # Generate clean response
        final_response = await responder.generate_response(
            task_id=state["task_id"],
            original_request=state["original_request"],
            worker_output=worker_output,
            has_artifacts=has_artifacts,
        )

        logger.info(
            "response_generated",
            task_id=str(state["task_id"]),
            response_length=len(final_response),
        )

        # Build response details for broadcast
        response_details = {
            "final_response": final_response,
            "has_artifacts": has_artifacts,
        }

        # Emit responder completed event
        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_COMPLETED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=state["task_id"],
                sequence_number=0,
                agent="responder",
                status=AgentStatus.COMPLETED,
                message="Response ready",
                details=response_details,
            )
        )

        return {
            "final_response": final_response,
        }

    except Exception as e:
        logger.error("generate_response_failed", error=str(e))
        # Fallback to worker output if responder fails
        milestones = state.get("milestones", [])
        fallback = "Task completed."
        if milestones:
            fallback = milestones[-1].get("worker_output") or "Task completed."
        return {
            "final_response": fallback,
            "error": str(e),
            "error_node": "generate_response",
        }
