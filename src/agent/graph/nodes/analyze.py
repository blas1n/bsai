"""Analyze task node for Architect agent.

This node uses the Architect agent to create hierarchical project plans
and converts them to the legacy milestone format for compatibility.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ArchitectAgent
from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.db.models.project_plan import ProjectPlan
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.events import AgentActivityEvent, AgentStatus, EventType
from agent.llm.schemas import PlanStatus
from agent.memory import get_memory_context

from ..state import AgentState, MilestoneData
from . import get_container, get_event_bus, get_memory_manager

logger = structlog.get_logger()


def _convert_plan_to_milestones(
    plan: ProjectPlan,
    sequence_offset: int = 0,
) -> list[MilestoneData]:
    """Convert ProjectPlan tasks to legacy milestone format.

    Temporary compatibility layer for gradual migration.
    Creates MilestoneData entries from the plan's task list.

    Args:
        plan: ProjectPlan database instance
        sequence_offset: Offset for milestone numbering

    Returns:
        List of MilestoneData dictionaries
    """
    milestones: list[MilestoneData] = []
    tasks: list[dict[str, Any]] = plan.plan_data.get("tasks", [])

    for task in tasks:
        # Parse complexity from string
        complexity_str = task.get("complexity", "MODERATE")
        try:
            complexity = TaskComplexity[complexity_str]
        except KeyError:
            complexity = TaskComplexity.MODERATE

        milestones.append(
            MilestoneData(
                id=uuid4(),  # Generate new UUID for milestone
                description=task.get("description", ""),
                complexity=complexity,
                acceptance_criteria=task.get("acceptance_criteria", ""),
                status=MilestoneStatus.PENDING,
                selected_model=None,
                generated_prompt=None,
                worker_output=None,
                qa_feedback=None,
                retry_count=0,
            )
        )

    return milestones


async def analyze_task_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Analyze task and create project plan using Architect agent.

    This is the entry node that creates a hierarchical project plan
    and converts it to milestones for the existing workflow.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session (per-request)

    Returns:
        Partial state with project_plan, milestones list and initial status
    """
    container = get_container(config)
    event_bus = get_event_bus(config)

    # Emit architect started event
    await event_bus.emit(
        AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=state["task_id"],  # Use task_id as placeholder
            sequence_number=0,
            agent="architect",
            status=AgentStatus.STARTED,
            message="Analyzing task and creating project plan",
        )
    )

    try:
        # Retrieve relevant memories for context using DI container
        memory_manager = get_memory_manager(config, session)
        relevant_memories, memory_context = await get_memory_context(
            manager=memory_manager,
            user_id=state["user_id"],
            original_request=state["original_request"],
        )

        # Get handover context from previous task (passed via context_messages)
        # This helps Architect understand what was done in the previous task
        handover_context = None
        context_messages = state.get("context_messages", [])
        for msg in context_messages:
            if msg.role == "system" and "Context from previous task" in msg.content:
                handover_context = msg.content
                break

        # Combine memory context with handover context
        combined_context = None
        if handover_context or memory_context:
            parts = []
            if handover_context:
                parts.append(handover_context)
            if memory_context:
                parts.append(memory_context)
            combined_context = "\n\n---\n\n".join(parts)

        # Get existing milestones from state (from previous tasks in session)
        existing_milestones: list[MilestoneData] = list(state.get("milestones", []))
        sequence_offset = state.get("milestone_sequence_offset", 0)

        # Clean up any existing milestones for this task (from failed retries)
        # This prevents unique constraint violations on (task_id, sequence_number)
        milestone_repo = MilestoneRepository(session)
        existing_task_milestones = await milestone_repo.get_by_task_id(state["task_id"])
        if existing_task_milestones:
            logger.info(
                "cleaning_up_existing_milestones",
                task_id=str(state["task_id"]),
                count=len(existing_task_milestones),
            )
            for old_milestone in existing_task_milestones:
                await milestone_repo.delete(old_milestone.id)
            await session.commit()

        # Create Architect agent and generate project plan
        architect = ArchitectAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
        )

        # Create hierarchical project plan
        project_plan = await architect.create_plan(
            task_id=state["task_id"],
            session_id=state["session_id"],
            original_request=state["original_request"],
            memory_context=combined_context,
            project_context=None,  # TODO: Add project context support
        )

        logger.info(
            "project_plan_created",
            task_id=str(state["task_id"]),
            plan_id=str(project_plan.id),
            structure_type=project_plan.structure_type,
            total_tasks=project_plan.total_tasks,
        )

        # Convert plan to milestones for legacy compatibility
        new_milestones = _convert_plan_to_milestones(project_plan, sequence_offset)

        # Persist milestones to database for compatibility with existing flow
        for i, milestone_data in enumerate(new_milestones):
            db_milestone = await milestone_repo.create(
                task_id=state["task_id"],
                sequence_number=sequence_offset + i,
                description=milestone_data["description"],
                complexity=milestone_data["complexity"],
                acceptance_criteria=milestone_data["acceptance_criteria"],
            )
            # Update milestone_data with actual DB ID
            milestone_data["id"] = db_milestone.id

        await session.commit()

        logger.debug(
            "milestones_committed",
            task_id=str(state["task_id"]),
            milestone_count=len(new_milestones),
        )

        # Combine existing milestones with new ones
        all_milestones = existing_milestones + new_milestones

        logger.info(
            "analyze_task_complete",
            task_id=str(state["task_id"]),
            plan_id=str(project_plan.id),
            new_milestone_count=len(new_milestones),
            total_milestone_count=len(all_milestones),
            sequence_offset=sequence_offset,
            has_handover_context=handover_context is not None,
            has_memory_context=memory_context is not None,
        )

        # Build milestone details for broadcast (only new milestones)
        milestone_details = {
            "plan_id": str(project_plan.id),
            "structure_type": project_plan.structure_type,
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
            ],
        }

        # Emit architect completed event with milestone details
        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_COMPLETED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=state["task_id"],
                sequence_number=0,
                agent="architect",
                status=AgentStatus.COMPLETED,
                message=f"Created project plan with {len(new_milestones)} tasks (total: {len(all_milestones)})",
                details=milestone_details,
            )
        )

        # Return combined state including new project_plan fields
        return {
            # New project plan fields
            "project_plan": project_plan,
            "plan_status": PlanStatus.DRAFT,
            # Legacy compatibility: milestones for existing flow
            "milestones": all_milestones,
            "current_milestone_index": len(existing_milestones),  # Start at first new milestone
            "task_status": TaskStatus.IN_PROGRESS,
            "retry_count": 0,
            # Include memory data in state
            "relevant_memories": relevant_memories,
            "memory_context": memory_context if memory_context else None,
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
