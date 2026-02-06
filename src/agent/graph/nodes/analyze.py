"""Analyze task node for Architect agent.

This node uses the Architect agent to create hierarchical project plans.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ArchitectAgent
from agent.db.models.enums import TaskStatus
from agent.events import AgentActivityEvent, AgentStatus, EventType
from agent.llm.schemas import PlanStatus
from agent.memory import get_memory_context

from ..state import AgentState
from . import get_container, get_event_bus, get_memory_manager

logger = structlog.get_logger()


async def analyze_task_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Analyze task and create project plan using Architect agent.

    This is the entry node that creates a hierarchical project plan.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session (per-request)

    Returns:
        Partial state with project_plan and initial status
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

        # Get first task ID from plan
        tasks = project_plan.plan_data.get("tasks", [])
        first_task_id = tasks[0]["id"] if tasks else None

        # Build task details for broadcast
        task_details = {
            "plan_id": str(project_plan.id),
            "structure_type": project_plan.structure_type,
            "tasks": [
                {
                    "id": t["id"],
                    "description": t.get("description", ""),
                    "complexity": t.get("complexity", "MODERATE"),
                    "acceptance_criteria": t.get("acceptance_criteria", ""),
                }
                for t in tasks
            ],
        }

        # Emit architect completed event with task details
        await event_bus.emit(
            AgentActivityEvent(
                type=EventType.AGENT_COMPLETED,
                session_id=state["session_id"],
                task_id=state["task_id"],
                milestone_id=state["task_id"],
                sequence_number=0,
                agent="architect",
                status=AgentStatus.COMPLETED,
                message=f"Created project plan with {len(tasks)} tasks",
                details=task_details,
            )
        )

        return {
            "project_plan": project_plan,
            "plan_status": PlanStatus.DRAFT,
            "current_task_id": first_task_id,
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
