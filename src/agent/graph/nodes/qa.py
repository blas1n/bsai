"""QA verification node."""

from __future__ import annotations

from typing import Any, cast

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import QAAgent, QADecision
from agent.db.models.enums import MilestoneStatus, TaskStatus
from agent.events import AgentActivityEvent, AgentStatus, EventType

from ..state import AgentState, MilestoneData
from . import check_task_cancelled, get_container, get_event_bus, get_ws_manager_optional

logger = structlog.get_logger()


async def verify_qa_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Validate worker output via QA agent.

    Performs independent validation of Worker output
    and provides structured feedback for improvements.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with QA decision and feedback
    """
    container = get_container(config)
    event_bus = get_event_bus(config)
    ws_manager = get_ws_manager_optional(config)  # Optional: for MCP stdio tools only

    # Check if task was cancelled before starting
    if await check_task_cancelled(session, state["task_id"]):
        logger.info("verify_qa_cancelled", task_id=str(state["task_id"]))
        return {
            "error": "Task cancelled by user",
            "error_node": "verify_qa",
            "task_status": TaskStatus.FAILED,
            "workflow_complete": True,
        }

    try:
        milestones = state.get("milestones")
        idx = state.get("current_milestone_index")

        if milestones is None or idx is None:
            return {"error": "No milestones available", "error_node": "verify_qa"}

        milestone = milestones[idx]
        retry_count = state.get("retry_count", 0)

        # Emit QA started event
        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_STARTED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=milestone["id"],
                sequence_number=idx + 1,
                agent="qa",
                status=AgentStatus.STARTED,
                message="Validating output quality",
            )
        )

        qa = QAAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
            ws_manager=ws_manager,
        )

        decision, feedback = await qa.validate_output(
            milestone_id=milestone["id"],
            milestone_description=milestone["description"],
            acceptance_criteria=milestone["acceptance_criteria"],
            worker_output=milestone["worker_output"] or "",
            user_id=state["user_id"],
            session_id=state["session_id"],
        )

        # Update milestone with QA result (immutable)
        updated_milestones = list(milestones)
        updated_milestone = dict(milestone)
        updated_milestone["qa_feedback"] = feedback

        if decision == QADecision.PASS:
            updated_milestone["status"] = MilestoneStatus.PASSED
        elif decision == QADecision.FAIL:
            updated_milestone["status"] = MilestoneStatus.FAILED
        # RETRY keeps IN_PROGRESS status

        updated_milestones[idx] = cast(MilestoneData, updated_milestone)

        logger.info(
            "qa_verified",
            milestone_index=idx,
            decision=decision.value,
            retry_count=retry_count,
        )

        # Broadcast QA completed with decision
        if decision == QADecision.PASS:
            qa_message = "Quality check passed"
        elif decision == QADecision.FAIL:
            qa_message = (
                f"Failed after max retries: {feedback[:50]}..."
                if feedback
                else "Failed after max retries"
            )
        else:  # RETRY
            qa_message = f"Retry needed: {feedback[:50]}..." if feedback else "Retry needed"

        # Build QA details for broadcast
        qa_details = {
            "decision": decision.value,
            "feedback": feedback,
            "acceptance_criteria": milestone["acceptance_criteria"],
            "attempt_number": retry_count + 1,
            "max_retries": 3,
        }

        # Emit QA completed event with decision
        qa_status = MilestoneStatus(updated_milestone["status"])
        # Determine agent status based on QA decision
        agent_status = (
            AgentStatus.COMPLETED if decision == QADecision.PASS else AgentStatus.COMPLETED
        )
        qa_details["milestone_status"] = qa_status.value
        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_COMPLETED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=milestone["id"],
                sequence_number=idx + 1,
                agent="qa",
                status=agent_status,
                message=qa_message,
                details=qa_details,
            )
        )

        return {
            "milestones": updated_milestones,
            "current_qa_decision": decision.value,
            "current_qa_feedback": feedback,
        }

    except Exception as e:
        logger.error("verify_qa_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "verify_qa",
        }
