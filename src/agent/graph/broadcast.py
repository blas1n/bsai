"""WebSocket broadcast utilities for workflow nodes.

Provides helper functions to broadcast agent status updates
during workflow execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from agent.api.schemas import (
    MilestoneProgressPayload,
    TaskProgressPayload,
    WSMessage,
    WSMessageType,
)
from agent.db.models.enums import MilestoneStatus

if TYPE_CHECKING:
    from agent.api.websocket.manager import ConnectionManager

logger = structlog.get_logger()


async def broadcast_agent_started(
    ws_manager: ConnectionManager | None,
    session_id: UUID,
    task_id: UUID,
    milestone_id: UUID,
    sequence_number: int,
    agent: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Broadcast agent started notification.

    Args:
        ws_manager: WebSocket connection manager
        session_id: Session ID for broadcast target
        task_id: Task ID
        milestone_id: Milestone ID
        sequence_number: Milestone sequence number (1-based)
        agent: Agent name (conductor, meta_prompter, worker, qa, summarizer)
        message: Status message
        details: Additional agent-specific details (e.g., milestones list, prompts)
    """
    if ws_manager is None:
        return

    try:
        await ws_manager.broadcast_to_session(
            session_id,
            WSMessage(
                type=WSMessageType.MILESTONE_PROGRESS,
                payload=MilestoneProgressPayload(
                    milestone_id=milestone_id,
                    task_id=task_id,
                    sequence_number=sequence_number,
                    status=MilestoneStatus.IN_PROGRESS,
                    agent=agent,
                    message=message,
                    details=details,
                ).model_dump(),
            ),
        )
        logger.debug(
            "broadcast_agent_started",
            agent=agent,
            milestone_id=str(milestone_id),
        )
    except Exception as e:
        logger.warning(
            "broadcast_agent_started_failed",
            agent=agent,
            error=str(e),
        )


async def broadcast_agent_completed(
    ws_manager: ConnectionManager | None,
    session_id: UUID,
    task_id: UUID,
    milestone_id: UUID,
    sequence_number: int,
    agent: str,
    message: str,
    status: MilestoneStatus = MilestoneStatus.IN_PROGRESS,
    details: dict[str, Any] | None = None,
) -> None:
    """Broadcast agent completed notification.

    Args:
        ws_manager: WebSocket connection manager
        session_id: Session ID for broadcast target
        task_id: Task ID
        milestone_id: Milestone ID
        sequence_number: Milestone sequence number (1-based)
        agent: Agent name
        message: Status message
        status: Milestone status after completion
        details: Additional agent-specific details (e.g., milestones list, prompts)
    """
    if ws_manager is None:
        return

    try:
        await ws_manager.broadcast_to_session(
            session_id,
            WSMessage(
                type=WSMessageType.MILESTONE_PROGRESS,
                payload=MilestoneProgressPayload(
                    milestone_id=milestone_id,
                    task_id=task_id,
                    sequence_number=sequence_number,
                    status=status,
                    agent=agent,
                    message=message,
                    details=details,
                ).model_dump(),
            ),
        )
        logger.debug(
            "broadcast_agent_completed",
            agent=agent,
            milestone_id=str(milestone_id),
        )
    except Exception as e:
        logger.warning(
            "broadcast_agent_completed_failed",
            agent=agent,
            error=str(e),
        )


async def broadcast_task_progress(
    ws_manager: ConnectionManager | None,
    session_id: UUID,
    task_id: UUID,
    current_milestone: int,
    total_milestones: int,
    current_milestone_title: str,
) -> None:
    """Broadcast task progress update.

    Args:
        ws_manager: WebSocket connection manager
        session_id: Session ID for broadcast target
        task_id: Task ID
        current_milestone: Current milestone index (0-based)
        total_milestones: Total number of milestones
        current_milestone_title: Title of current milestone
    """
    if ws_manager is None:
        return

    try:
        progress = (current_milestone + 1) / total_milestones if total_milestones > 0 else 0.0
        await ws_manager.broadcast_to_session(
            session_id,
            WSMessage(
                type=WSMessageType.TASK_PROGRESS,
                payload=TaskProgressPayload(
                    task_id=task_id,
                    current_milestone=current_milestone + 1,  # 1-based for UI
                    total_milestones=total_milestones,
                    progress=progress,
                    current_milestone_title=current_milestone_title,
                ).model_dump(),
            ),
        )
        logger.debug(
            "broadcast_task_progress",
            current=current_milestone + 1,
            total=total_milestones,
        )
    except Exception as e:
        logger.warning(
            "broadcast_task_progress_failed",
            error=str(e),
        )


async def broadcast_milestone_completed(
    ws_manager: ConnectionManager | None,
    session_id: UUID,
    task_id: UUID,
    milestone_id: UUID,
    sequence_number: int,
    status: MilestoneStatus,
) -> None:
    """Broadcast milestone completion.

    Args:
        ws_manager: WebSocket connection manager
        session_id: Session ID for broadcast target
        task_id: Task ID
        milestone_id: Milestone ID
        sequence_number: Milestone sequence number (1-based)
        status: Final milestone status (passed/failed)
    """
    if ws_manager is None:
        return

    message_type = (
        WSMessageType.MILESTONE_COMPLETED
        if status == MilestoneStatus.PASSED
        else WSMessageType.MILESTONE_FAILED
    )

    try:
        await ws_manager.broadcast_to_session(
            session_id,
            WSMessage(
                type=message_type,
                payload=MilestoneProgressPayload(
                    milestone_id=milestone_id,
                    task_id=task_id,
                    sequence_number=sequence_number,
                    status=status,
                    agent="workflow",
                    message=f"Milestone {status.value}",
                ).model_dump(),
            ),
        )
        logger.debug(
            "broadcast_milestone_completed",
            milestone_id=str(milestone_id),
            status=status.value,
        )
    except Exception as e:
        logger.warning(
            "broadcast_milestone_completed_failed",
            error=str(e),
        )


async def broadcast_milestone_retry(
    ws_manager: ConnectionManager | None,
    session_id: UUID,
    task_id: UUID,
    milestone_id: UUID,
    sequence_number: int,
    retry_count: int,
    feedback: str | None = None,
) -> None:
    """Broadcast milestone retry notification.

    Args:
        ws_manager: WebSocket connection manager
        session_id: Session ID for broadcast target
        task_id: Task ID
        milestone_id: Milestone ID
        sequence_number: Milestone sequence number (1-based)
        retry_count: Current retry count
        feedback: QA feedback for retry
    """
    if ws_manager is None:
        return

    try:
        message = f"Retry {retry_count}/3"
        if feedback:
            message += f": {feedback[:100]}"

        await ws_manager.broadcast_to_session(
            session_id,
            WSMessage(
                type=WSMessageType.MILESTONE_RETRY,
                payload=MilestoneProgressPayload(
                    milestone_id=milestone_id,
                    task_id=task_id,
                    sequence_number=sequence_number,
                    status=MilestoneStatus.IN_PROGRESS,
                    agent="qa",
                    message=message,
                ).model_dump(),
            ),
        )
        logger.debug(
            "broadcast_milestone_retry",
            milestone_id=str(milestone_id),
            retry_count=retry_count,
        )
    except Exception as e:
        logger.warning(
            "broadcast_milestone_retry_failed",
            error=str(e),
        )
