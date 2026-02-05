"""QA verification node.

Supports both:
1. New flow: project_plan with tasks
2. Legacy flow: milestones list
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import QAAgent, QADecision
from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.utils import get_task_by_id, get_tasks_from_plan
from agent.memory import store_qa_learning

from ..state import AgentState, MilestoneData, update_milestone
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

    Supports both:
    - New flow: project_plan with tasks
    - Legacy flow: milestones list

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
        # Check if using new project_plan flow or legacy milestones flow
        project_plan = state.get("project_plan")
        milestones = state.get("milestones")
        idx = state.get("current_milestone_index")

        # Extract task/milestone information based on flow type
        if project_plan:
            current_task_id: str | None = state.get("current_task_id")  # type: ignore[assignment]
            tasks = get_tasks_from_plan(project_plan)
            task = get_task_by_id(tasks, current_task_id) if current_task_id else None

            if task is None:
                return {"error": "No task available in project plan", "error_node": "verify_qa"}

            # Create milestone-like dict for QA compatibility
            complexity_str = task.get("complexity", "MODERATE")
            try:
                task_complexity = TaskComplexity[complexity_str]
            except KeyError:
                task_complexity = TaskComplexity.MODERATE

            milestone: MilestoneData = {
                "id": state["task_id"],  # Use task_id as milestone_id
                "description": task.get("description", ""),
                "complexity": task_complexity,
                "acceptance_criteria": task.get("acceptance_criteria", ""),
                "status": MilestoneStatus.IN_PROGRESS,
                "selected_model": None,
                "generated_prompt": None,
                "worker_output": state.get("current_output"),
                "qa_feedback": None,
                "retry_count": state.get("retry_count", 0),
            }
            idx = idx if idx is not None else 0
        else:
            if milestones is None or idx is None:
                return {"error": "No milestones available", "error_node": "verify_qa"}
            milestone = milestones[idx]
            task = None

        retry_count = state.get("retry_count", 0)

        # Emit QA started event
        await ctx.emit_started(
            agent="qa",
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone["id"],
            sequence_number=idx + 1,
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
            milestone_id=milestone["id"],
            milestone_description=milestone["description"],
            acceptance_criteria=milestone["acceptance_criteria"],
            worker_output=milestone["worker_output"] or "",
            user_id=state["user_id"],
            session_id=state["session_id"],
        )

        # Determine new status based on decision
        new_status = milestone["status"]
        if decision == QADecision.PASS:
            new_status = MilestoneStatus.PASSED
        elif decision == QADecision.FAIL:
            new_status = MilestoneStatus.FAILED
        # RETRY keeps IN_PROGRESS status

        # Update milestone with QA result (only for legacy flow)
        updated_milestones = None
        if milestones:
            updated_milestones = list(milestones)
            updated_milestones[idx] = update_milestone(
                milestone,
                qa_feedback=feedback,
                status=new_status,
            )

        logger.info(
            "qa_verified",
            milestone_index=idx,
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
                    improved_output=milestone["worker_output"] or "",
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
            "milestone_status": new_status.value,
        }

        # Emit QA completed event with decision
        await ctx.emit_completed(
            agent="qa",
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone["id"],
            sequence_number=idx + 1,
            message=qa_message,
            details=qa_details,
        )

        # Build result with flow-specific fields
        result: dict[str, Any] = {
            "current_qa_decision": decision.value,
            "current_qa_feedback": feedback,
        }

        # Include milestones only for legacy flow
        if updated_milestones:
            result["milestones"] = updated_milestones

        return result

    except Exception as e:
        logger.error("verify_qa_failed", error=str(e))
        return ctx.error_response("verify_qa", e)
