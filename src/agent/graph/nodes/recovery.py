"""Recovery node for graceful failure handling.

Handles task failures by either:
1. Attempting a strategy retry with a completely different approach
2. Generating a detailed failure report if retry is exhausted
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ConductorAgent
from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.events import AgentActivityEvent, AgentStatus, EventType

from ..state import AgentState, MilestoneData
from . import get_container, get_event_bus

logger = structlog.get_logger()


def _summarize_failed_approach(milestones: list[MilestoneData]) -> str:
    """Summarize the approach that was attempted.

    Args:
        milestones: List of milestones that were attempted

    Returns:
        Human-readable summary of the approach
    """
    if not milestones:
        return "No approach was attempted"

    parts = []
    for i, m in enumerate(milestones, 1):
        status = m.get("status", MilestoneStatus.PENDING)
        if hasattr(status, "value"):
            status_str = status.value
        else:
            status_str = str(status)

        parts.append(f"{i}. {m['description']} [{status_str}]")

    return "\n".join(parts)


def _collect_failure_reasons(state: AgentState) -> list[str]:
    """Collect all failure reasons from state.

    Args:
        state: Current workflow state

    Returns:
        List of failure reason strings
    """
    reasons = []

    # Get the main error
    if state.get("error"):
        reasons.append(f"Error: {state['error']}")

    # Get QA feedback from milestones
    milestones = state.get("milestones", [])
    for m in milestones:
        qa_feedback = m.get("qa_feedback")
        if qa_feedback:
            reasons.append(f"QA Feedback for '{m['description'][:50]}...': {qa_feedback}")

    # Get replan reason if any
    if state.get("replan_reason"):
        reasons.append(f"Replan reason: {state['replan_reason']}")

    if not reasons:
        reasons.append("Unknown failure - no specific error recorded")

    return reasons


def _create_milestones_from_plan(
    plan: list[dict[str, str | TaskComplexity]],
) -> list[MilestoneData]:
    """Convert Conductor plan output to MilestoneData list.

    Args:
        plan: List of milestone dicts from Conductor

    Returns:
        List of MilestoneData objects
    """
    milestones: list[MilestoneData] = []

    for m in plan:
        complexity = m["complexity"]
        if isinstance(complexity, TaskComplexity):
            # Already a TaskComplexity enum, use as-is
            pass
        elif isinstance(complexity, str):
            complexity = TaskComplexity[complexity]
        else:
            # Fallback for unexpected types
            complexity = TaskComplexity.MODERATE

        milestones.append(
            MilestoneData(
                id=uuid4(),
                description=str(m["description"]),
                complexity=complexity,
                acceptance_criteria=str(m.get("acceptance_criteria", "")),
                status=MilestoneStatus.PENDING,
                selected_model=None,
                generated_prompt=None,
                worker_output=None,
                qa_feedback=None,
                retry_count=0,
            )
        )

    return milestones


async def recovery_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Handle task failure with strategy retry or failure report.

    This node is called when a task has failed (max retries or replans exceeded).
    It implements a two-phase recovery:
    1. First failure: Try a completely different strategy
    2. Second failure: Generate a detailed failure report for the user

    Args:
        state: Current workflow state
        config: LangGraph config
        session: Database session

    Returns:
        Partial state update
    """
    container = get_container(config)
    event_bus = get_event_bus(config)

    task_id = state["task_id"]
    session_id = state["session_id"]

    # Check if we've already attempted a strategy retry
    strategy_retry_attempted = state.get("strategy_retry_attempted", False)

    if not strategy_retry_attempted:
        # First failure - attempt strategy retry
        logger.info(
            "recovery_strategy_retry_start",
            task_id=str(task_id),
        )

        # Emit recovery started event
        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_STARTED,
                session_id=session_id,
                task_id=task_id,
                milestone_id=task_id,  # Use task_id as placeholder
                sequence_number=0,
                agent="recovery",
                status=AgentStatus.STARTED,
                message="Attempting alternative strategy",
            )
        )

        try:
            conductor = ConductorAgent(
                llm_client=container.llm_client,
                router=container.router,
                prompt_manager=container.prompt_manager,
                session=session,
            )

            # Collect failure context
            failed_approach = _summarize_failed_approach(state.get("milestones", []))
            failure_reasons = _collect_failure_reasons(state)

            # Get new plan with different strategy
            new_plan = await conductor.rethink_strategy(
                task_id=task_id,
                original_request=state["original_request"],
                failed_approach=failed_approach,
                failure_reasons=failure_reasons,
            )

            # Convert to MilestoneData
            new_milestones = _create_milestones_from_plan(new_plan)

            logger.info(
                "recovery_strategy_retry_complete",
                task_id=str(task_id),
                new_milestone_count=len(new_milestones),
            )

            # Emit recovery completed event
            await event_bus.emit(
                AgentActivityEvent(
                    type=EventType.AGENT_COMPLETED,
                    session_id=session_id,
                    task_id=task_id,
                    milestone_id=task_id,
                    sequence_number=0,
                    agent="recovery",
                    status=AgentStatus.COMPLETED,
                    message=f"Trying alternative approach with {len(new_milestones)} new steps",
                    details={"new_milestone_count": len(new_milestones)},
                )
            )

            # Return state for retry with new strategy
            return {
                "strategy_retry_attempted": True,
                "milestones": new_milestones,
                "current_milestone_index": 0,
                "retry_count": 0,
                "replan_count": 0,
                "error": None,  # Clear error for fresh start
                "error_node": None,
                "needs_replan": False,
                "replan_reason": None,
                "workflow_complete": False,
            }

        except Exception as e:
            logger.error(
                "recovery_strategy_retry_failed",
                task_id=str(task_id),
                error=str(e),
            )
            # Fall through to failure report
            strategy_retry_attempted = True

    # Strategy retry already attempted or failed - prepare failure report
    logger.info(
        "recovery_failure_report_prepare",
        task_id=str(task_id),
    )

    # Build failure context for Responder
    partial_results: list[dict[str, Any]] = []

    # Extract any partial results from passed milestones
    milestones = state.get("milestones", [])
    if isinstance(milestones, list):
        for m in milestones:
            status = m.get("status")
            if status == MilestoneStatus.PASSED:
                partial_results.append(
                    {
                        "description": m["description"],
                        "output": m.get("worker_output", ""),
                    }
                )

    failure_context: dict[str, Any] = {
        "original_request": state["original_request"],
        "attempted_milestones": milestones,
        "final_error": state.get("error"),
        "partial_results": partial_results,
    }

    # Emit failure report preparation event
    await event_bus.emit(
        AgentActivityEvent(
            type=EventType.AGENT_COMPLETED,
            session_id=session_id,
            task_id=task_id,
            milestone_id=task_id,
            sequence_number=0,
            agent="recovery",
            status=AgentStatus.COMPLETED,
            message="Preparing detailed failure report",
        )
    )

    return {
        "strategy_retry_attempted": True,
        "failure_context": failure_context,
        "workflow_complete": True,
    }
