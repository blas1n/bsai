"""QA verification node."""

from __future__ import annotations

from typing import Any, cast

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import QAAgent, QADecision
from agent.db.models.enums import MilestoneStatus

from ..broadcast import broadcast_agent_completed, broadcast_agent_started
from ..state import AgentState, MilestoneData
from . import get_container, get_ws_manager

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
    ws_manager = get_ws_manager(config)

    try:
        milestones = state.get("milestones")
        idx = state.get("current_milestone_index")

        if milestones is None or idx is None:
            return {"error": "No milestones available", "error_node": "verify_qa"}

        milestone = milestones[idx]
        retry_count = state.get("retry_count", 0)

        # Broadcast QA started
        await broadcast_agent_started(
            ws_manager=ws_manager,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone["id"],
            sequence_number=idx + 1,
            agent="qa",
            message="Validating output quality",
        )

        qa = QAAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
        )

        decision, feedback = await qa.validate_output(
            milestone_id=milestone["id"],
            milestone_description=milestone["description"],
            acceptance_criteria=milestone["acceptance_criteria"],
            worker_output=milestone["worker_output"] or "",
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

        # Use the status from the typed MilestoneData
        qa_status = MilestoneStatus(updated_milestone["status"])
        await broadcast_agent_completed(
            ws_manager=ws_manager,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone["id"],
            sequence_number=idx + 1,
            agent="qa",
            message=qa_message,
            status=qa_status,
            details=qa_details,
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
