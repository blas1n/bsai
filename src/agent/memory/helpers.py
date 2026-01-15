"""Memory helper functions for workflow nodes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from agent.db.models.enums import MemoryType

if TYPE_CHECKING:
    from .manager import LongTermMemoryManager

logger = structlog.get_logger()


async def get_memory_context(
    manager: LongTermMemoryManager,
    user_id: str,
    original_request: str,
    limit: int = 3,
) -> tuple[list[dict[str, Any]], str]:
    """Retrieve relevant memories for context.

    Args:
        manager: LongTermMemoryManager instance from DI container
        user_id: User identifier
        original_request: Current task request
        limit: Maximum memories to retrieve

    Returns:
        Tuple of (memory list, formatted context string)
    """
    try:
        results = await manager.search_similar(
            user_id=user_id,
            query=original_request,
            limit=limit,
            memory_types=[MemoryType.TASK_RESULT, MemoryType.LEARNING],
        )

        memories: list[dict[str, Any]] = [
            {
                "id": str(m.id),
                "summary": m.summary,
                "type": m.memory_type,
                "similarity": score,
            }
            for m, score in results
        ]

        context = await manager.get_relevant_context(
            user_id=user_id,
            current_task=original_request,
            limit=limit,
        )

        logger.info(
            "memory_context_retrieved",
            user_id=user_id,
            memory_count=len(memories),
        )

        return memories, context

    except Exception as e:
        logger.warning("memory_retrieval_failed", error=str(e))
        return [], ""


async def store_task_memory(
    manager: LongTermMemoryManager,
    user_id: str,
    session_id: UUID,
    task_id: UUID,
    original_request: str,
    final_response: str,
    milestones: list[dict[str, Any]],
) -> None:
    """Store completed task result as memory.

    Args:
        manager: LongTermMemoryManager instance from DI container
        user_id: User identifier
        session_id: Session UUID
        task_id: Task UUID
        original_request: Original user request
        final_response: Final task response
        milestones: List of completed milestones
    """
    try:
        # Generate milestones summary
        milestones_summary = "\n".join(
            f"- {m['description']}: {m['status'].value if hasattr(m['status'], 'value') else m['status']}"
            for m in milestones
        )

        await manager.store_task_result(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            original_request=original_request,
            final_result=final_response or "",
            milestones_summary=milestones_summary,
        )

        logger.info(
            "task_result_stored_to_memory",
            task_id=str(task_id),
            user_id=user_id,
        )

    except Exception as e:
        logger.warning("memory_storage_failed", error=str(e))


async def store_qa_learning(
    manager: LongTermMemoryManager,
    user_id: str,
    session_id: UUID,
    task_id: UUID,
    previous_output: str,
    qa_feedback: str,
    improved_output: str,
) -> None:
    """Store QA learning when retry succeeds.

    Args:
        manager: LongTermMemoryManager instance from DI container
        user_id: User identifier
        session_id: Session UUID
        task_id: Task UUID
        previous_output: Output before QA
        qa_feedback: QA feedback
        improved_output: Improved output after retry
    """
    try:
        await manager.store_qa_learning(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            original_output=previous_output,
            qa_feedback=qa_feedback,
            improved_output=improved_output,
        )

        logger.info(
            "qa_learning_stored",
            task_id=str(task_id),
        )

    except Exception as e:
        logger.warning("qa_learning_storage_failed", error=str(e))
