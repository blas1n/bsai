"""Response generation node."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ResponderAgent
from agent.graph.utils import get_tasks_from_plan

from ..state import AgentState
from . import NodeContext

logger = structlog.get_logger()


async def generate_response_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Generate final user-facing response via Responder agent.

    Called after all tasks are complete to create a clean,
    localized response for the user.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with final_response
    """
    ctx = NodeContext.from_config(config, session)

    # Check if we need to generate a failure report
    failure_context = state.get("failure_context")
    if failure_context:
        logger.info(
            "response_generating_failure_report",
            task_id=str(state["task_id"]),
        )
        try:
            responder = ResponderAgent(
                llm_client=ctx.container.llm_client,
                router=ctx.container.router,
                prompt_manager=ctx.container.prompt_manager,
                session=session,
            )

            # Cast failure_context since state.get returns object type
            failure_context_dict: dict[str, Any] = (
                failure_context if isinstance(failure_context, dict) else {}
            )
            failure_report = await responder.generate_failure_report(
                task_id=state["task_id"],
                original_request=state["original_request"],
                failure_context=failure_context_dict,
            )

            # Emit failure report event
            await ctx.emit_completed(
                agent="responder",
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=state["task_id"],
                sequence_number=0,
                message="Failure report generated",
                details={"is_failure_report": True},
            )

            return {
                "final_response": failure_report,
            }
        except Exception as e:
            logger.error("failure_report_generation_failed", error=str(e))
            return {
                "final_response": f"Task could not be completed. Error: {state.get('error', 'Unknown error')}",
            }

    # If there was an error without failure_context
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
        await ctx.emit_started(
            agent="responder",
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=state["task_id"],  # Use task_id as placeholder
            sequence_number=0,
            message="Generating final response",
        )

        responder = ResponderAgent(
            llm_client=ctx.container.llm_client,
            router=ctx.container.router,
            prompt_manager=ctx.container.prompt_manager,
            session=session,
        )

        # Get worker output from project plan tasks
        worker_output = _get_worker_output_from_plan(state)
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
        await ctx.emit_completed(
            agent="responder",
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=state["task_id"],
            sequence_number=0,
            message="Response ready",
            details=response_details,
        )

        return {
            "final_response": final_response,
        }

    except Exception as e:
        logger.error("generate_response_failed", error=str(e))
        # Fallback to worker output if responder fails
        fallback = _get_worker_output_from_plan(state) or "Task completed."
        return {
            "final_response": fallback,
            "error": str(e),
            "error_node": "generate_response",
        }


def _get_worker_output_from_plan(state: AgentState) -> str:
    """Extract worker output from project plan tasks.

    Args:
        state: Current workflow state

    Returns:
        Combined worker output from all completed tasks
    """
    project_plan = state.get("project_plan")
    if not project_plan:
        return ""

    tasks = get_tasks_from_plan(project_plan)
    if not tasks:
        return ""

    # Combine outputs from all completed tasks
    worker_output_parts = []
    for task in tasks:
        if task.get("status") == "completed":
            output = task.get("worker_output")
            if output:
                description = task.get("description", task.get("id", "Task"))
                worker_output_parts.append(f"## {description}\n{output}")

    return "\n\n".join(worker_output_parts) if worker_output_parts else ""
