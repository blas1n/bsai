"""Task Summary node for generating task completion summary.

The Task Summary Agent is responsible for:
1. Summarizing all milestones completed in the current task
2. Listing artifacts created/modified
3. Generating handover context for the next task's Conductor

This runs after all milestones are complete, before Responder.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.db.repository.artifact_repo import ArtifactRepository
from agent.db.repository.task_repo import TaskRepository

from ..state import AgentState

logger = structlog.get_logger()


async def task_summary_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Generate task completion summary for Responder and next task context.

    This node:
    1. Collects all milestone results
    2. Lists all artifacts created in this task
    3. Creates a summary that:
       - Helps Responder generate a complete user response
       - Provides context for the next task's Conductor

    Args:
        state: Current workflow state
        config: LangGraph config
        session: Database session

    Returns:
        Partial state with task_summary
    """
    all_milestones = state.get("milestones", [])
    task_id = state["task_id"]
    original_request = state.get("original_request", "")
    sequence_offset = state.get("milestone_sequence_offset", 0)

    # Filter milestones to only include those from the current task
    # (milestones after the offset are the new ones created for this task)
    current_task_milestones = (
        all_milestones[sequence_offset:] if sequence_offset > 0 else all_milestones
    )

    logger.info(
        "task_summary_started",
        task_id=str(task_id),
        total_milestone_count=len(all_milestones),
        current_task_milestone_count=len(current_task_milestones),
        sequence_offset=sequence_offset,
    )

    try:
        # Collect milestone summaries (only for current task's milestones)
        milestone_summaries = []
        for idx, milestone in enumerate(current_task_milestones):
            status = milestone.get("status", "unknown")
            description = milestone.get("description", "")
            worker_output = milestone.get("worker_output", "")

            milestone_summaries.append(
                {
                    "index": sequence_offset + idx + 1,  # Use session-wide sequence number
                    "description": description,
                    "status": str(status),
                    "output": worker_output,  # Full output for Responder
                }
            )

        # Get artifacts created in this task
        artifact_repo = ArtifactRepository(session)
        task_artifacts = await artifact_repo.get_by_task_id(task_id)

        artifact_list = []
        for artifact in task_artifacts:
            file_path = (
                f"{artifact.path}/{artifact.filename}" if artifact.path else artifact.filename
            )
            artifact_list.append(
                {
                    "path": file_path,
                    "kind": artifact.kind,
                    "size": len(artifact.content) if artifact.content else 0,
                }
            )

        # Build task summary
        task_summary = {
            "original_request": original_request,
            "milestone_count": len(current_task_milestones),
            "milestones": milestone_summaries,
            "artifact_count": len(artifact_list),
            "artifacts": artifact_list,
        }

        # Build handover context for next task's Conductor
        # This is a concise summary that helps Conductor understand previous work
        handover_lines = [
            "## Previous Task Summary",
            f"Request: {original_request}",
            "",
            f"### Completed Work ({len(current_task_milestones)} milestones):",
        ]

        for ms in milestone_summaries:
            handover_lines.append(f"- {ms['description']} [{ms['status']}]")

        if artifact_list:
            handover_lines.append("")
            handover_lines.append(f"### Artifacts Created ({len(artifact_list)} files):")
            for art_info in artifact_list:
                handover_lines.append(f"- {art_info['path']} ({art_info['kind']})")

        handover_context = "\n".join(handover_lines)

        # Store handover context in task_summary for Responder
        task_summary["handover_context"] = handover_context

        # Save handover context to DB for next task's Conductor to retrieve
        task_repo = TaskRepository(session)
        await task_repo.save_handover_context(task_id, handover_context)

        logger.info(
            "task_summary_completed",
            task_id=str(task_id),
            milestone_count=len(current_task_milestones),
            artifact_count=len(artifact_list),
            handover_saved=True,
        )

        return {
            "task_summary": task_summary,
        }

    except Exception as e:
        logger.error("task_summary_failed", task_id=str(task_id), error=str(e))
        # Don't fail the workflow, just return empty summary
        return {
            "task_summary": {
                "original_request": original_request,
                "milestone_count": len(current_task_milestones),
                "milestones": [],
                "artifact_count": 0,
                "artifacts": [],
                "error": str(e),
            },
        }
