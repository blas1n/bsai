"""LLM selection and prompt generation nodes."""

from __future__ import annotations

from typing import Any, cast

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ConductorAgent, MetaPrompterAgent
from agent.db.models.enums import MilestoneStatus

from ..broadcast import broadcast_agent_completed, broadcast_agent_started, broadcast_task_progress
from ..state import AgentState, MilestoneData
from . import get_container, get_ws_manager

logger = structlog.get_logger()


async def select_llm_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Select LLM for current milestone.

    Uses the Conductor's model selection logic based on
    milestone complexity and user preferences.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with selected model in milestone
    """
    container = get_container(config)
    ws_manager = get_ws_manager(config)

    try:
        milestones = state.get("milestones")
        idx = state.get("current_milestone_index")

        if milestones is None or idx is None:
            return {"error": "No milestones available", "error_node": "select_llm"}

        milestone = milestones[idx]

        # Broadcast task progress
        await broadcast_task_progress(
            ws_manager=ws_manager,
            session_id=state["session_id"],
            task_id=state["task_id"],
            current_milestone=idx,
            total_milestones=len(milestones),
            current_milestone_title=milestone["description"][:50],
        )

        conductor = ConductorAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
        )

        model_name = await conductor.select_model_for_milestone(
            complexity=milestone["complexity"],
        )

        # Update milestone with selected model (immutable update)
        updated_milestones = list(milestones)
        updated_milestone = dict(milestone)
        updated_milestone["selected_model"] = model_name
        updated_milestone["status"] = MilestoneStatus.IN_PROGRESS
        updated_milestones[idx] = cast(MilestoneData, updated_milestone)

        logger.info(
            "llm_selected",
            milestone_index=idx,
            model=model_name,
            complexity=milestone["complexity"].name,
        )

        return {"milestones": updated_milestones}

    except Exception as e:
        logger.error("select_llm_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "select_llm",
        }


async def generate_prompt_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Generate optimized prompt via MetaPrompter.

    Only called for MODERATE+ complexity tasks where
    prompt optimization provides significant value.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with generated prompt
    """
    container = get_container(config)
    ws_manager = get_ws_manager(config)

    try:
        milestones = state.get("milestones")
        idx = state.get("current_milestone_index")

        if milestones is None or idx is None:
            return {"error": "No milestones available", "error_node": "generate_prompt"}

        milestone = milestones[idx]

        # Broadcast meta_prompter started
        await broadcast_agent_started(
            ws_manager=ws_manager,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone["id"],
            sequence_number=idx + 1,
            agent="meta_prompter",
            message="Optimizing prompt for task execution",
        )

        meta_prompter = MetaPrompterAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
        )

        # Build context string from recent messages
        context = None
        context_messages = state.get("context_messages", [])
        if context_messages:
            context_parts = [f"{m.role}: {m.content}" for m in context_messages[-5:]]
            context = "\n".join(context_parts)

        prompt = await meta_prompter.generate_prompt(
            milestone_id=milestone["id"],
            milestone_description=milestone["description"],
            milestone_complexity=milestone["complexity"],
            acceptance_criteria=milestone["acceptance_criteria"],
            context=context,
        )

        # Update milestone with prompt (immutable)
        updated_milestones = list(milestones)
        updated_milestone = dict(milestone)
        updated_milestone["generated_prompt"] = prompt
        updated_milestones[idx] = cast(MilestoneData, updated_milestone)

        logger.info(
            "prompt_generated",
            milestone_index=idx,
            prompt_length=len(prompt),
        )

        # Build prompt details for broadcast
        prompt_details = {
            "generated_prompt": prompt,
            "prompt_length": len(prompt),
            "milestone_description": milestone["description"],
        }

        # Broadcast meta_prompter completed with prompt details
        await broadcast_agent_completed(
            ws_manager=ws_manager,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone["id"],
            sequence_number=idx + 1,
            agent="meta_prompter",
            message="Prompt optimized",
            details=prompt_details,
        )

        return {
            "milestones": updated_milestones,
            "current_prompt": prompt,
        }

    except Exception as e:
        logger.error("generate_prompt_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "generate_prompt",
        }
