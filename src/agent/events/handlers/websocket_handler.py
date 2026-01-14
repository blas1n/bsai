"""WebSocket event handler.

Converts domain events to WebSocket messages and broadcasts them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import structlog

from agent.api.schemas import (
    BreakpointCurrentState,
    BreakpointHitPayload,
    LLMChunkPayload,
    LLMCompletePayload,
    MilestoneProgressPayload,
    TaskCompletedPayload,
    TaskFailedPayload,
    TaskProgressPayload,
    TaskStartedPayload,
    WSMessage,
    WSMessageType,
)
from agent.events.types import (
    AgentActivityEvent,
    BreakpointHitEvent,
    ContextCompressedEvent,
    Event,
    EventType,
    LLMChunkEvent,
    LLMCompleteEvent,
    MilestoneRetryEvent,
    MilestoneStatusChangedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskProgressEvent,
    TaskStartedEvent,
)

if TYPE_CHECKING:
    from agent.api.websocket.manager import ConnectionManager

logger = structlog.get_logger()


class WebSocketEventHandler:
    """Converts events to WebSocket messages and broadcasts them.

    This handler is responsible for translating domain events into
    the WebSocket protocol format understood by the frontend.
    """

    def __init__(self, ws_manager: ConnectionManager) -> None:
        """Initialize with WebSocket manager.

        Args:
            ws_manager: ConnectionManager for broadcasting
        """
        self.ws_manager = ws_manager

    async def handle(self, event: Event) -> None:
        """Handle an event by converting to WS message and broadcasting.

        Args:
            event: Event to handle
        """
        ws_message = self._to_ws_message(event)
        if ws_message is None:
            return

        try:
            await self.ws_manager.broadcast_to_session(
                event.session_id,
                ws_message,
            )
            logger.debug(
                "ws_event_broadcast",
                event_type=str(event.type),
                ws_type=str(ws_message.type),
                session_id=str(event.session_id),
            )
        except Exception as e:
            logger.warning(
                "ws_broadcast_failed",
                event_type=str(event.type),
                error=str(e),
            )

    def _to_ws_message(self, event: Event) -> WSMessage | None:
        """Convert event to WebSocket message.

        Args:
            event: Event to convert

        Returns:
            WSMessage or None if event type is not handled
        """
        match event.type:
            # Task events
            case EventType.TASK_STARTED:
                return self._task_started(cast(TaskStartedEvent, event))
            case EventType.TASK_PROGRESS:
                return self._task_progress(cast(TaskProgressEvent, event))
            case EventType.TASK_COMPLETED:
                return self._task_completed(cast(TaskCompletedEvent, event))
            case EventType.TASK_FAILED:
                return self._task_failed(cast(TaskFailedEvent, event))

            # Agent activity events
            case EventType.AGENT_STARTED | EventType.AGENT_COMPLETED | EventType.AGENT_FAILED:
                return self._agent_activity(cast(AgentActivityEvent, event))

            # Milestone events
            case EventType.MILESTONE_STATUS_CHANGED:
                return self._milestone_status_changed(cast(MilestoneStatusChangedEvent, event))
            case EventType.MILESTONE_COMPLETED:
                return self._milestone_completed(cast(MilestoneStatusChangedEvent, event))
            case EventType.MILESTONE_FAILED:
                return self._milestone_failed(cast(MilestoneStatusChangedEvent, event))
            case EventType.MILESTONE_RETRY:
                return self._milestone_retry(cast(MilestoneRetryEvent, event))

            # LLM streaming events
            case EventType.LLM_CHUNK:
                return self._llm_chunk(cast(LLMChunkEvent, event))
            case EventType.LLM_COMPLETE:
                return self._llm_complete(cast(LLMCompleteEvent, event))

            # Context events
            case EventType.CONTEXT_COMPRESSED:
                return self._context_compressed(cast(ContextCompressedEvent, event))

            # Breakpoint events
            case EventType.BREAKPOINT_HIT:
                return self._breakpoint_hit(cast(BreakpointHitEvent, event))

            case _:
                logger.debug("unhandled_event_type", event_type=str(event.type))
                return None

        return None

    # =========================================================================
    # Task Event Converters
    # =========================================================================

    def _task_started(self, event: TaskStartedEvent) -> WSMessage:
        """Convert TaskStartedEvent to WS message."""
        return WSMessage(
            type=WSMessageType.TASK_STARTED,
            payload=TaskStartedPayload(
                task_id=event.task_id,
                session_id=event.session_id,
                original_request=event.original_request,
                milestone_count=event.milestone_count,
                previous_milestones=event.previous_milestones,
                trace_url=event.trace_url,
            ).model_dump(),
        )

    def _task_progress(self, event: TaskProgressEvent) -> WSMessage:
        """Convert TaskProgressEvent to WS message."""
        return WSMessage(
            type=WSMessageType.TASK_PROGRESS,
            payload=TaskProgressPayload(
                task_id=event.task_id,
                current_milestone=event.current_milestone,
                total_milestones=event.total_milestones,
                progress=event.progress,
                current_milestone_title=event.current_milestone_title,
            ).model_dump(),
        )

    def _task_completed(self, event: TaskCompletedEvent) -> WSMessage:
        """Convert TaskCompletedEvent to WS message."""
        return WSMessage(
            type=WSMessageType.TASK_COMPLETED,
            payload=TaskCompletedPayload(
                task_id=event.task_id,
                final_result=event.final_result,
                total_tokens=event.total_input_tokens + event.total_output_tokens,
                total_cost_usd=event.total_cost_usd,
                duration_seconds=event.duration_seconds,
                trace_url=event.trace_url,
            ).model_dump(),
        )

    def _task_failed(self, event: TaskFailedEvent) -> WSMessage:
        """Convert TaskFailedEvent to WS message."""
        return WSMessage(
            type=WSMessageType.TASK_FAILED,
            payload=TaskFailedPayload(
                task_id=event.task_id,
                error=event.error,
                failed_milestone=event.failed_milestone,
            ).model_dump(),
        )

    # =========================================================================
    # Agent Activity Event Converters
    # =========================================================================

    def _agent_activity(self, event: AgentActivityEvent) -> WSMessage:
        """Convert AgentActivityEvent to MILESTONE_PROGRESS message.

        The status field is now EXPLICIT - frontend doesn't need heuristics.
        """
        return WSMessage(
            type=WSMessageType.MILESTONE_PROGRESS,
            payload=MilestoneProgressPayload(
                milestone_id=event.milestone_id,
                task_id=event.task_id,
                sequence_number=event.sequence_number,
                # Pass explicit status - frontend uses this directly
                status=str(event.status),
                agent=event.agent,
                message=event.message,
                details=event.details or {},
            ).model_dump(),
        )

    # =========================================================================
    # Milestone Event Converters
    # =========================================================================

    def _milestone_status_changed(self, event: MilestoneStatusChangedEvent) -> WSMessage:
        """Convert MilestoneStatusChangedEvent to appropriate WS message."""
        # Determine message type based on new status
        if event.new_status == "passed":
            msg_type = WSMessageType.MILESTONE_COMPLETED
        elif event.new_status == "failed":
            msg_type = WSMessageType.MILESTONE_FAILED
        else:
            msg_type = WSMessageType.MILESTONE_PROGRESS

        return WSMessage(
            type=msg_type,
            payload=MilestoneProgressPayload(
                milestone_id=event.milestone_id,
                task_id=event.task_id,
                sequence_number=event.sequence_number,
                status=str(event.new_status),
                agent=event.agent,
                message=event.message,
                details=event.details or {},
            ).model_dump(),
        )

    def _milestone_completed(self, event: MilestoneStatusChangedEvent) -> WSMessage:
        """Convert milestone completed event."""
        return WSMessage(
            type=WSMessageType.MILESTONE_COMPLETED,
            payload=MilestoneProgressPayload(
                milestone_id=event.milestone_id,
                task_id=event.task_id,
                sequence_number=event.sequence_number,
                status="passed",
                agent=event.agent,
                message=event.message,
            ).model_dump(),
        )

    def _milestone_failed(self, event: MilestoneStatusChangedEvent) -> WSMessage:
        """Convert milestone failed event."""
        return WSMessage(
            type=WSMessageType.MILESTONE_FAILED,
            payload=MilestoneProgressPayload(
                milestone_id=event.milestone_id,
                task_id=event.task_id,
                sequence_number=event.sequence_number,
                status="failed",
                agent=event.agent,
                message=event.message,
            ).model_dump(),
        )

    def _milestone_retry(self, event: MilestoneRetryEvent) -> WSMessage:
        """Convert MilestoneRetryEvent to WS message."""
        message = f"Retry {event.retry_count}/{event.max_retries}"
        if event.feedback:
            message += f": {event.feedback[:100]}"

        return WSMessage(
            type=WSMessageType.MILESTONE_RETRY,
            payload=MilestoneProgressPayload(
                milestone_id=event.milestone_id,
                task_id=event.task_id,
                sequence_number=event.sequence_number,
                status="in_progress",
                agent="qa",
                message=message,
            ).model_dump(),
        )

    # =========================================================================
    # LLM Streaming Event Converters
    # =========================================================================

    def _llm_chunk(self, event: LLMChunkEvent) -> WSMessage:
        """Convert LLMChunkEvent to WS message."""
        return WSMessage(
            type=WSMessageType.LLM_CHUNK,
            payload=LLMChunkPayload(
                task_id=event.task_id,
                milestone_id=event.milestone_id,
                chunk=event.chunk,
                chunk_index=event.chunk_index,
                agent=event.agent,
            ).model_dump(),
        )

    def _llm_complete(self, event: LLMCompleteEvent) -> WSMessage:
        """Convert LLMCompleteEvent to WS message."""
        return WSMessage(
            type=WSMessageType.LLM_COMPLETE,
            payload=LLMCompletePayload(
                task_id=event.task_id,
                milestone_id=event.milestone_id,
                full_content=event.full_content,
                tokens_used=event.tokens_used,
                agent=event.agent,
            ).model_dump(),
        )

    # =========================================================================
    # Context Event Converters
    # =========================================================================

    def _context_compressed(self, event: ContextCompressedEvent) -> WSMessage:
        """Convert ContextCompressedEvent to WS message."""
        return WSMessage(
            type=WSMessageType.CONTEXT_COMPRESSED,
            payload={
                "task_id": str(event.task_id),
                "old_message_count": event.old_message_count,
                "new_message_count": event.new_message_count,
                "tokens_saved_estimate": event.tokens_saved_estimate,
            },
        )

    # =========================================================================
    # Breakpoint Event Converters
    # =========================================================================

    def _breakpoint_hit(self, event: BreakpointHitEvent) -> WSMessage:
        """Convert BreakpointHitEvent to WS message."""
        current_state = BreakpointCurrentState(
            current_milestone_index=event.current_milestone_index,
            total_milestones=event.total_milestones,
            milestones=event.milestones,
            last_worker_output=event.last_worker_output,
            last_qa_result=event.last_qa_result,
        )

        return WSMessage(
            type=WSMessageType.BREAKPOINT_HIT,
            payload=BreakpointHitPayload(
                task_id=event.task_id,
                session_id=event.session_id,
                node_name=event.node_name,
                agent_type=event.agent_type,
                current_state=current_state,
            ).model_dump(),
        )
