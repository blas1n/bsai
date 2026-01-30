"""Replan node for dynamic plan modification.

Implements the ReAct pattern by allowing the Conductor to modify
the execution plan based on observations from Worker execution
and plan viability assessments from QA.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.core.conductor import ConductorAgent
from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.events import EventType
from agent.events.types import PlanModificationEvent
from agent.graph.state import AgentState, MilestoneData
from agent.llm.schemas import MilestoneModification

from . import get_container, get_event_bus

logger = structlog.get_logger()


async def replan_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Execute replanning based on observations and QA feedback.

    This node is triggered when QA determines the plan needs revision.
    It uses the Conductor to analyze the situation and modify the plan.

    Args:
        state: Current workflow state
        config: LangGraph config
        session: Database session

    Returns:
        Partial state with updated milestones and replan metadata
    """
    container = get_container(config)
    event_bus = get_event_bus(config)
    settings = get_agent_settings()

    task_id = state["task_id"]
    session_id = state["session_id"]

    # Check replan iteration limit (from config)
    replan_count = state.get("replan_count", 0)
    max_replans = settings.max_replan_iterations

    if replan_count >= max_replans:
        logger.warning(
            "max_replans_exceeded",
            task_id=str(task_id),
            replan_count=replan_count,
            max_allowed=max_replans,
        )
        return {
            "error": "Maximum replan iterations exceeded",
            "error_node": "replan",
            "workflow_complete": True,
        }

    logger.info(
        "replan_started",
        task_id=str(task_id),
        replan_iteration=replan_count + 1,
        reason=state.get("replan_reason"),
    )

    try:
        # Gather context for replanning
        milestones = state.get("milestones", [])
        idx = state.get("current_milestone_index", 0)
        observations = state.get("current_observations", [])
        qa_feedback = state.get("current_qa_feedback", "")
        replan_reason = state.get("replan_reason", "Plan viability issue")

        # Create Conductor agent
        conductor = ConductorAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
        )

        # Get replan output from Conductor
        replan_output = await conductor.replan_based_on_execution(
            task_id=task_id,
            original_request=state["original_request"],
            current_milestones=milestones,
            current_milestone_index=idx,
            worker_observations=observations,
            qa_feedback=qa_feedback or "",
            replan_reason=replan_reason or "Plan viability issue",
            previous_replans=state.get("plan_modifications"),
        )

        # Apply modifications to milestones
        updated_milestones = _apply_modifications(
            milestones=milestones,
            modifications=replan_output.modifications,
            current_index=idx,
            replan_iteration=replan_count + 1,
        )

        # Persist milestone changes to database
        milestone_repo = MilestoneRepository(session)
        await _persist_milestone_changes(
            repo=milestone_repo,
            task_id=task_id,
            milestones=updated_milestones,
            modifications=replan_output.modifications,
        )

        # Commit milestone changes to ensure they're persisted before subsequent nodes
        # reference them (e.g., generate_prompt_node creates generated_prompts
        # with milestone_id foreign key)
        await session.commit()

        # Build modification record for history
        modification_record = {
            "iteration": replan_count + 1,
            "trigger_milestone_index": idx,
            "reason": replan_reason,
            "analysis": replan_output.analysis,
            "modifications": [m.model_dump() for m in replan_output.modifications],
            "confidence": replan_output.confidence,
            "reasoning": replan_output.reasoning,
        }

        # Update plan modifications history
        plan_modifications = state.get("plan_modifications", [])
        plan_modifications = [*plan_modifications, modification_record]

        # Emit plan modification event
        current_milestone_id = milestones[idx]["id"] if idx < len(milestones) else task_id
        await event_bus.emit(
            PlanModificationEvent(
                type=EventType.PLAN_MODIFIED,
                session_id=session_id,
                task_id=task_id,
                milestone_id=current_milestone_id,
                replan_iteration=replan_count + 1,
                modifications_count=len(replan_output.modifications),
                reason=replan_reason or "Plan viability issue",
                confidence=replan_output.confidence,
            )
        )

        logger.info(
            "replan_completed",
            task_id=str(task_id),
            replan_iteration=replan_count + 1,
            modifications_count=len(replan_output.modifications),
            new_milestone_count=len(updated_milestones),
            confidence=replan_output.confidence,
        )

        return {
            "milestones": updated_milestones,
            "replan_count": replan_count + 1,
            "plan_modifications": plan_modifications,
            "plan_confidence": replan_output.confidence,
            "needs_replan": False,
            "replan_reason": None,
            "current_observations": [],  # Clear after processing
            # Reset retry state for re-execution
            "retry_count": 0,
            "current_qa_decision": None,
            "current_qa_feedback": None,
        }

    except Exception as e:
        logger.error(
            "replan_failed",
            task_id=str(task_id),
            error=str(e),
        )
        return {
            "error": str(e),
            "error_node": "replan",
            "workflow_complete": True,
        }


def _apply_modifications(
    milestones: list[MilestoneData],
    modifications: list[MilestoneModification],
    current_index: int,
    replan_iteration: int,
) -> list[MilestoneData]:
    """Apply plan modifications to milestone list.

    Args:
        milestones: Current milestone list
        modifications: List of MilestoneModification objects
        current_index: Current milestone index
        replan_iteration: Current replan iteration number

    Returns:
        Updated milestone list with modifications applied
    """
    # Create mutable copy
    updated = list(milestones)

    # Track index shifts from additions/removals
    index_offset = 0

    for mod in modifications:
        if mod.action == "ADD" and mod.new_milestone:
            # Determine insert position
            insert_idx = mod.target_index if mod.target_index is not None else len(updated)
            # Adjust for previous modifications
            insert_idx = max(current_index + 1, insert_idx + index_offset)

            # Create new milestone data
            new_milestone: MilestoneData = {
                "id": uuid4(),
                "description": mod.new_milestone.description,
                "complexity": TaskComplexity[mod.new_milestone.complexity],
                "acceptance_criteria": mod.new_milestone.acceptance_criteria,
                "status": MilestoneStatus.PENDING,
                "selected_model": None,
                "generated_prompt": None,
                "worker_output": None,
                "qa_feedback": None,
                "retry_count": 0,
                "is_modified": True,
                "added_at_replan": replan_iteration,
            }
            updated.insert(insert_idx, new_milestone)
            index_offset += 1

        elif mod.action == "MODIFY" and mod.target_index is not None and mod.new_milestone:
            target_idx = mod.target_index + index_offset
            # Only modify milestones after current index
            if target_idx < len(updated) and target_idx > current_index:
                old = updated[target_idx]
                modified_milestone: MilestoneData = {
                    "id": old["id"],
                    "description": mod.new_milestone.description,
                    "complexity": TaskComplexity[mod.new_milestone.complexity],
                    "acceptance_criteria": mod.new_milestone.acceptance_criteria,
                    "status": old["status"],
                    "selected_model": old["selected_model"],
                    "generated_prompt": old["generated_prompt"],
                    "worker_output": old["worker_output"],
                    "qa_feedback": old["qa_feedback"],
                    "retry_count": old["retry_count"],
                    "is_modified": True,
                }
                updated[target_idx] = modified_milestone

        elif mod.action == "REMOVE" and mod.target_index is not None:
            target_idx = mod.target_index + index_offset
            # Only remove milestones after current index
            if target_idx < len(updated) and target_idx > current_index:
                del updated[target_idx]
                index_offset -= 1

        elif mod.action == "REORDER" and mod.target_index is not None:
            # TODO: REORDER action is not fully implemented.
            # Current behavior: Only marks the milestone as modified without actual reordering.
            # Full implementation requires MilestoneModification schema to include
            # both source_index and destination_index fields.
            target_idx = mod.target_index + index_offset
            if target_idx < len(updated) and target_idx > current_index:
                old = updated[target_idx]
                reordered_milestone: MilestoneData = {
                    "id": old["id"],
                    "description": old["description"],
                    "complexity": old["complexity"],
                    "acceptance_criteria": old["acceptance_criteria"],
                    "status": old["status"],
                    "selected_model": old["selected_model"],
                    "generated_prompt": old["generated_prompt"],
                    "worker_output": old["worker_output"],
                    "qa_feedback": old["qa_feedback"],
                    "retry_count": old["retry_count"],
                    "is_modified": True,
                }
                updated[target_idx] = reordered_milestone
                logger.warning(
                    "reorder_action_not_fully_implemented",
                    target_index=mod.target_index,
                    reason="REORDER only marks milestone as modified, does not actually reorder",
                )

    return updated


async def _persist_milestone_changes(
    repo: MilestoneRepository,
    task_id: UUID,
    milestones: list[MilestoneData],
    modifications: list[MilestoneModification],
) -> None:
    """Persist milestone changes to database.

    This function handles ADD, REMOVE, and MODIFY operations on milestones.
    To avoid unique constraint violations on (task_id, sequence_number),
    we first process removals, then create new milestones, and finally
    update sequence numbers for all milestones.

    Args:
        repo: Milestone repository
        task_id: Task ID
        milestones: Updated milestone list (with correct order)
        modifications: List of modifications made
    """
    # Step 1: Process REMOVE modifications first
    for mod in modifications:
        if mod.action == "REMOVE" and mod.target_index is not None:
            # Find the milestone ID to delete
            # Note: This is best-effort as indices may have shifted
            try:
                original_milestones = await repo.get_by_task_id(task_id)
                if mod.target_index < len(original_milestones):
                    milestone_to_delete = original_milestones[mod.target_index]
                    await repo.delete(milestone_to_delete.id)
            except Exception as e:
                logger.error(
                    "milestone_delete_failed",
                    error=str(e),
                    target_index=mod.target_index,
                )
                # Re-raise to prevent workflow from continuing with inconsistent state
                raise

    # Step 2: Create new milestones with temporary high sequence numbers
    # to avoid unique constraint violations during the update phase
    temp_sequence_base = 10000  # Use high numbers that won't conflict
    for i, milestone in enumerate(milestones):
        if milestone.get("added_at_replan") and milestone.get("is_modified"):
            # Check if this milestone already exists in DB
            try:
                existing = await repo.get_by_id(milestone["id"])
                if not existing:
                    await repo.create(
                        id=milestone["id"],
                        task_id=task_id,
                        sequence_number=temp_sequence_base + i,  # Temporary high number
                        title=f"Milestone {i + 1}",
                        description=milestone["description"],
                        complexity=milestone["complexity"].value,
                        acceptance_criteria=milestone["acceptance_criteria"],
                    )
                    logger.debug(
                        "milestone_created",
                        milestone_id=str(milestone["id"]),
                        temp_sequence=temp_sequence_base + i,
                    )
            except Exception as e:
                logger.error(
                    "milestone_create_failed",
                    error=str(e),
                    milestone_id=str(milestone["id"]),
                )
                # Re-raise to prevent workflow from continuing with invalid milestone IDs
                raise

    # Step 3: Update all milestone sequence numbers to match new order
    # First, set all to temporary high values to avoid conflicts
    for i, milestone in enumerate(milestones):
        try:
            await repo.update(milestone["id"], sequence_number=temp_sequence_base + i)
        except Exception as e:
            logger.warning(
                "milestone_sequence_temp_update_failed",
                error=str(e),
                milestone_id=str(milestone["id"]),
            )
            # Continue - milestone might have been just created with temp sequence

    # Then set to final values
    for i, milestone in enumerate(milestones):
        try:
            await repo.update(milestone["id"], sequence_number=i + 1)
        except Exception as e:
            logger.error(
                "milestone_sequence_update_failed",
                error=str(e),
                milestone_id=str(milestone["id"]),
                target_sequence=i + 1,
            )
            # Re-raise to prevent workflow from continuing with inconsistent state
            raise
