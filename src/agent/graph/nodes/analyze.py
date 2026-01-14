"""Analyze task node for Conductor agent."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ConductorAgent
from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.events import AgentActivityEvent, AgentStatus, EventType

from ..state import AgentState, MilestoneData
from . import get_container, get_event_bus

logger = structlog.get_logger()


async def analyze_task_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Analyze task and create milestones via Conductor.

    This is the entry node that breaks down the user request
    into manageable milestones with complexity assessments.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session (per-request)

    Returns:
        Partial state with milestones list and initial status
    """
    container = get_container(config)
    event_bus = get_event_bus(config)

    # Emit conductor started event
    await event_bus.emit(
        AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=state["task_id"],  # Use task_id as placeholder
            sequence_number=0,
            agent="conductor",
            status=AgentStatus.STARTED,
            message="Analyzing task and planning milestones",
        )
    )

    try:
        conductor = ConductorAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
        )

        milestones_raw = await conductor.analyze_and_plan(
            task_id=state["task_id"],
            original_request=state["original_request"],
        )

        # Fetch persisted milestones from database to get actual IDs
        milestone_repo = MilestoneRepository(session)
        db_milestones = await milestone_repo.get_by_task_id(state["task_id"])

        # Get existing milestones from state (from previous tasks in session)
        existing_milestones: list[MilestoneData] = list(state.get("milestones", []))
        sequence_offset = state.get("milestone_sequence_offset", 0)

        # Convert to MilestoneData format with actual DB IDs
        new_milestones: list[MilestoneData] = []
        for i, m in enumerate(milestones_raw):
            # Get DB ID if available, otherwise use placeholder
            db_id = db_milestones[i].id if i < len(db_milestones) else UUID(int=i)

            # Ensure complexity is TaskComplexity
            complexity = m["complexity"]
            if not isinstance(complexity, TaskComplexity):
                complexity = TaskComplexity(complexity)

            new_milestones.append(
                MilestoneData(
                    id=db_id,
                    description=str(m["description"]),
                    complexity=complexity,
                    acceptance_criteria=str(m["acceptance_criteria"]),
                    status=MilestoneStatus.PENDING,
                    selected_model=None,
                    generated_prompt=None,
                    worker_output=None,
                    qa_feedback=None,
                    retry_count=0,
                )
            )

        # Combine existing milestones with new ones
        all_milestones = existing_milestones + new_milestones

        logger.info(
            "analyze_task_complete",
            task_id=str(state["task_id"]),
            new_milestone_count=len(new_milestones),
            total_milestone_count=len(all_milestones),
            sequence_offset=sequence_offset,
        )

        # Build milestone details for broadcast (only new milestones)
        milestone_details = {
            "milestones": [
                {
                    "index": sequence_offset + i + 1,  # Continue numbering from offset
                    "description": m["description"],
                    "complexity": (
                        m["complexity"].value
                        if hasattr(m["complexity"], "value")
                        else str(m["complexity"])
                    ),
                    "acceptance_criteria": m["acceptance_criteria"],
                }
                for i, m in enumerate(new_milestones)
            ]
        }

        # Emit conductor completed event with milestone details
        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_COMPLETED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=state["task_id"],
                sequence_number=0,
                agent="conductor",
                status=AgentStatus.COMPLETED,
                message=f"Created {len(new_milestones)} milestones (total: {len(all_milestones)})",
                details=milestone_details,
            )
        )

        # Return combined milestones, starting index after existing ones
        return {
            "milestones": all_milestones,
            "current_milestone_index": len(existing_milestones),  # Start at first new milestone
            "task_status": TaskStatus.IN_PROGRESS,
            "retry_count": 0,
        }

    except Exception as e:
        logger.error(
            "analyze_task_failed",
            task_id=str(state["task_id"]),
            error=str(e),
        )
        return {
            "error": str(e),
            "error_node": "analyze_task",
            "task_status": TaskStatus.FAILED,
            "workflow_complete": True,
        }
