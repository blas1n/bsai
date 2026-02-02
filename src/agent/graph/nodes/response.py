"""Response generation node."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ResponderAgent

from ..state import AgentState
from . import NodeContext

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

            failure_report = await responder.generate_failure_report(
                task_id=state["task_id"],
                original_request=state["original_request"],
                failure_context=failure_context,
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

    # If there was an error without failure_context (legacy path)
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

        # Use task_summary if available (from task_summary node)
        # This contains summaries of ALL milestones, not just the last one
        task_summary = state.get("task_summary")

        if task_summary:
            # Build comprehensive worker output from task summary
            worker_output_parts = []

            # Add milestone summaries
            for milestone in task_summary.get("milestones", []):
                milestone_text = f"## {milestone['description']}\n{milestone['output']}"
                worker_output_parts.append(milestone_text)

            worker_output = "\n\n".join(worker_output_parts)

            # Check artifacts from task summary
            has_artifacts = bool(task_summary.get("artifacts"))
        else:
            # Fallback: Get worker output from last milestone (backward compatibility)
            milestones = state.get("milestones", [])
            worker_output = ""
            if milestones:
                last_milestone = milestones[-1]
                worker_output = last_milestone.get("worker_output") or ""
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
        milestones = state.get("milestones", [])
        fallback = "Task completed."
        if milestones:
            fallback = milestones[-1].get("worker_output") or "Task completed."
        return {
            "final_response": fallback,
            "error": str(e),
            "error_node": "generate_response",
        }
