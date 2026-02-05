"""QA verification node.

Validates worker output using the QA agent.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import QAAgent, QADecision
from agent.graph.utils import get_task_by_id, get_tasks_from_plan
from agent.memory import store_qa_learning

from ..state import AgentState
from . import NodeContext

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
    ctx = NodeContext.from_config(config, session)

    # Check if task was cancelled before starting
    if await ctx.check_cancelled(state["task_id"]):
        logger.info("verify_qa_cancelled", task_id=str(state["task_id"]))
        return ctx.cancelled_response("verify_qa")

    try:
        project_plan = state.get("project_plan")
        if not project_plan:
            return {"error": "No project_plan available", "error_node": "verify_qa"}

        current_task_id = state.get("current_task_id")
        tasks = get_tasks_from_plan(project_plan)
        task = get_task_by_id(tasks, current_task_id) if current_task_id else None

        if task is None:
            return {"error": "No task available in project plan", "error_node": "verify_qa"}

        task_idx = 0
        for i, t in enumerate(tasks):
            if t.get("id") == current_task_id:
                task_idx = i
                break

        retry_count = state.get("retry_count", 0)
        worker_output = state.get("current_output") or task.get("worker_output", "")

        # Emit QA started event
        await ctx.emit_started(
            agent="qa",
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=state["task_id"],
            sequence_number=task_idx + 1,
            message="Validating output quality",
        )

        qa = QAAgent(
            llm_client=ctx.container.llm_client,
            router=ctx.container.router,
            prompt_manager=ctx.container.prompt_manager,
            session=session,
            ws_manager=ctx.ws_manager,
        )

        decision, feedback, qa_output = await qa.validate_output(
            milestone_id=state["task_id"],
            milestone_description=task.get("description", ""),
            acceptance_criteria=task.get("acceptance_criteria", ""),
            worker_output=worker_output,
            user_id=state["user_id"],
            session_id=state["session_id"],
        )

        logger.info(
            "qa_verified",
            task_index=task_idx,
            decision=decision.value,
            retry_count=retry_count,
            plan_viability=qa_output.plan_viability,
        )

        # Store QA learning when retry succeeds (pass after at least one retry)
        if decision == QADecision.PASS and retry_count > 0:
            previous_feedback = state.get("current_qa_feedback", "")
            if previous_feedback:
                await store_qa_learning(
                    manager=ctx.memory_manager,
                    user_id=state["user_id"],
                    session_id=state["session_id"],
                    task_id=state["task_id"],
                    previous_output=state.get("current_output") or "",
                    qa_feedback=previous_feedback,
                    improved_output=worker_output,
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
            "acceptance_criteria": task.get("acceptance_criteria", ""),
            "attempt_number": retry_count + 1,
            "max_retries": 3,
        }

        # Emit QA completed event with decision
        await ctx.emit_completed(
            agent="qa",
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=state["task_id"],
            sequence_number=task_idx + 1,
            message=qa_message,
            details=qa_details,
        )

        return {
            "current_qa_decision": decision.value,
            "current_qa_feedback": feedback,
        }

    except Exception as e:
        logger.error("verify_qa_failed", error=str(e))
        return ctx.error_response("verify_qa", e)
