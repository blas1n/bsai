"""Logging event handler for observability.

Logs all events with structured data for debugging and monitoring.
"""

from __future__ import annotations

import structlog

from bsai.events.types import Event, EventType

logger = structlog.get_logger()


class LoggingEventHandler:
    """Logs all events for observability.

    Subscribes to all events (global handler) and logs them
    with appropriate log levels based on event type.
    """

    def __init__(self, log_level: str = "debug") -> None:
        """Initialize logging handler.

        Args:
            log_level: Default log level for events (debug, info, warning)
        """
        self.log_level = log_level

    async def handle(self, event: Event) -> None:
        """Log the event with structured data.

        Args:
            event: Event to log
        """
        log_data: dict[str, str | int | None] = {
            "event_type": str(event.type),
            "session_id": str(event.session_id),
            "task_id": str(event.task_id),
            "timestamp": event.timestamp.isoformat(),
        }

        # Add event-specific fields
        extra_fields = self._extract_extra_fields(event)
        log_data.update(extra_fields)

        # Determine log level based on event type
        level = self._get_log_level(event.type)

        if level == "error":
            logger.error("event_logged", **log_data)
        elif level == "warning":
            logger.warning("event_logged", **log_data)
        elif level == "info":
            logger.info("event_logged", **log_data)
        else:
            logger.debug("event_logged", **log_data)

    def _get_log_level(self, event_type: EventType) -> str:
        """Determine log level based on event type.

        Args:
            event_type: Type of event

        Returns:
            Log level string
        """
        # Errors get error level
        if event_type in (
            EventType.TASK_FAILED,
            EventType.MILESTONE_FAILED,
            EventType.AGENT_FAILED,
        ):
            return "error"

        # Completions get info level
        if event_type in (
            EventType.TASK_COMPLETED,
            EventType.MILESTONE_COMPLETED,
        ):
            return "info"

        # Retries get warning level
        if event_type == EventType.MILESTONE_RETRY:
            return "warning"

        # Everything else uses default level
        return self.log_level

    def _extract_extra_fields(self, event: Event) -> dict[str, str | int | None]:
        """Extract additional loggable fields from event.

        Args:
            event: Event to extract fields from

        Returns:
            Dictionary of extra fields
        """
        extra: dict[str, str | int | None] = {}

        # Common fields that many events have - use getattr for type safety
        if (milestone_id := getattr(event, "milestone_id", None)) is not None:
            extra["milestone_id"] = str(milestone_id)
        if (seq_num := getattr(event, "sequence_number", None)) is not None:
            extra["sequence_number"] = seq_num
        if (agent := getattr(event, "agent", None)) is not None:
            extra["agent"] = agent
        if (status := getattr(event, "status", None)) is not None:
            extra["status"] = str(status)
        if (msg := getattr(event, "message", None)) is not None:
            # Truncate long messages
            extra["message"] = msg[:200] if len(msg) > 200 else msg
        if (error := getattr(event, "error", None)) is not None:
            extra["error"] = error

        return extra
