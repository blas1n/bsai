"""Analyze task node for Conductor agent."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ConductorAgent
from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.events import AgentActivityEvent, AgentStatus, EventType
from agent.memory import get_memory_context

from ..state import AgentState, MilestoneData
from . import get_container, get_event_bus, get_memory_manager

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
        # Retrieve relevant memories for context using DI container
        memory_manager = get_memory_manager(config, session)
        relevant_memories, memory_context = await get_memory_context(
            manager=memory_manager,
            user_id=state["user_id"],
            original_request=state["original_request"],
        )

        # Get handover context from previous task (passed via context_messages)
        # This helps Conductor understand what was done in the previous task
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
            for m in existing_task_milestones:
                await milestone_repo.delete(m.id)
            await session.commit()

        conductor = ConductorAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
        )

        # Pass sequence_offset to conductor so DB records have correct sequence numbers
        milestones_raw = await conductor.analyze_and_plan(
            task_id=state["task_id"],
            original_request=state["original_request"],
            memory_context=combined_context,
            sequence_offset=sequence_offset,
        )

        # Commit milestones to ensure they're persisted before subsequent nodes
        # reference them (e.g., generate_prompt_node creates generated_prompts
        # with milestone_id foreign key)
        await session.commit()

        logger.debug(
            "milestones_committed",
            task_id=str(state["task_id"]),
            milestone_count=len(milestones_raw),
        )

        # Fetch persisted milestones from database to get actual IDs
        db_milestones = await milestone_repo.get_by_task_id(state["task_id"])

        logger.debug(
            "milestones_fetched_from_db",
            task_id=str(state["task_id"]),
            fetched_count=len(db_milestones),
            milestone_ids=[str(m.id) for m in db_milestones],
        )

        # Convert to MilestoneData format with actual DB IDs
        new_milestones: list[MilestoneData] = []
        for i, m in enumerate(milestones_raw):
            # Get DB ID if available, otherwise generate a random UUID
            # (this should rarely happen if conductor properly persists milestones)
            if i < len(db_milestones):
                db_id = db_milestones[i].id
            else:
                db_id = uuid4()
                logger.warning(
                    "milestone_missing_db_id",
                    task_id=str(state["task_id"]),
                    milestone_index=i,
                    fallback_id=str(db_id),
                    message="Generated fallback UUID - conductor may not have persisted milestone",
                )

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
            has_handover_context=handover_context is not None,
            has_memory_context=memory_context is not None,
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
