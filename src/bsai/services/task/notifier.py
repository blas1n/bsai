"""Task event notification service.

Handles WebSocket broadcasting for task lifecycle events.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import structlog

from bsai.api.schemas import (
    PreviousMilestoneInfo,
    TaskCompletedPayload,
    TaskFailedPayload,
    TaskStartedPayload,
    WSMessage,
    WSMessageType,
)
from bsai.api.websocket.manager import ConnectionManager

logger = structlog.get_logger()


class TaskNotifier:
    """Handles WebSocket notifications for task events.

    Responsible for broadcasting task lifecycle events to connected clients.
    """

    def __init__(self, ws_manager: ConnectionManager) -> None:
        """Initialize task notifier.

        Args:
            ws_manager: WebSocket connection manager for broadcasting
        """
        self.ws_manager = ws_manager

    async def notify_started(
        self,
        session_id: UUID,
        task_id: UUID,
        original_request: str,
        milestone_count: int = 0,
        previous_milestones: list[PreviousMilestoneInfo] | None = None,
    ) -> None:
        """Notify that a task has started.

        Args:
            session_id: Session ID
            task_id: Task ID
            original_request: The original user request
            milestone_count: Number of milestones planned
            previous_milestones: Previous milestones for context
        """
        await self.ws_manager.broadcast_to_session(
            session_id,
            WSMessage(
                type=WSMessageType.TASK_STARTED,
                payload=TaskStartedPayload(
                    task_id=task_id,
                    session_id=session_id,
                    original_request=original_request,
                    milestone_count=milestone_count,
                    previous_milestones=previous_milestones or [],
                ).model_dump(),
            ),
        )

        logger.debug(
            "task_started_notification_sent",
            session_id=str(session_id),
            task_id=str(task_id),
        )

    async def notify_completed(
        self,
        session_id: UUID,
        task_id: UUID,
        final_result: str,
        total_tokens: int,
        total_cost_usd: Decimal,
        duration_seconds: float,
    ) -> None:
        """Notify that a task has completed successfully.

        Args:
            session_id: Session ID
            task_id: Task ID
            final_result: The final result text
            total_tokens: Total tokens used
            total_cost_usd: Total cost in USD
            duration_seconds: Task duration in seconds
        """
        await self.ws_manager.broadcast_to_session(
            session_id,
            WSMessage(
                type=WSMessageType.TASK_COMPLETED,
                payload=TaskCompletedPayload(
                    task_id=task_id,
                    final_result=final_result or "Task completed",
                    total_tokens=total_tokens,
                    total_cost_usd=total_cost_usd,
                    duration_seconds=duration_seconds,
                ).model_dump(),
            ),
        )

        logger.debug(
            "task_completed_notification_sent",
            session_id=str(session_id),
            task_id=str(task_id),
        )

    async def notify_failed(
        self,
        session_id: UUID,
        task_id: UUID,
        error: str,
        failed_milestone: int | None = None,
    ) -> None:
        """Notify that a task has failed.

        Args:
            session_id: Session ID
            task_id: Task ID
            error: Error message
            failed_milestone: Index of the failed milestone (if applicable)
        """
        await self.ws_manager.broadcast_to_session(
            session_id,
            WSMessage(
                type=WSMessageType.TASK_FAILED,
                payload=TaskFailedPayload(
                    task_id=task_id,
                    error=error,
                    failed_milestone=failed_milestone,
                ).model_dump(),
            ),
        )

        logger.debug(
            "task_failed_notification_sent",
            session_id=str(session_id),
            task_id=str(task_id),
            error=error,
        )
