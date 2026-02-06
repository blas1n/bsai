"""EventBus implementation for async event handling.

Provides a pub/sub mechanism for decoupling event emitters from handlers.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog

from .types import Event, EventType

logger = structlog.get_logger()

EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """Async event bus with type-based routing.

    Features:
    - Subscribe to specific event types or all events
    - Parallel handler execution
    - Error isolation (one handler failure doesn't affect others)
    - Structured logging
    """

    def __init__(self) -> None:
        """Initialize empty handler registry."""
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._global_handlers: list[EventHandler] = []

    def subscribe(self, event_type: EventType | str, handler: EventHandler) -> None:
        """Subscribe handler to a specific event type.

        Args:
            event_type: Event type to subscribe to
            handler: Async function to call when event is emitted
        """
        event_key = str(event_type)
        self._handlers[event_key].append(handler)
        logger.debug("event_handler_subscribed", event_type=event_key)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe handler to all events.

        Useful for logging, metrics, or audit trails.

        Args:
            handler: Async function to call for every event
        """
        self._global_handlers.append(handler)
        logger.debug("global_event_handler_subscribed")

    def unsubscribe(self, event_type: EventType | str, handler: EventHandler) -> bool:
        """Unsubscribe handler from a specific event type.

        Args:
            event_type: Event type to unsubscribe from
            handler: Handler to remove

        Returns:
            True if handler was found and removed
        """
        event_key = str(event_type)
        handlers = self._handlers.get(event_key, [])
        if handler in handlers:
            handlers.remove(handler)
            return True
        return False

    def unsubscribe_all(self, handler: EventHandler) -> bool:
        """Unsubscribe handler from global events.

        Args:
            handler: Handler to remove

        Returns:
            True if handler was found and removed
        """
        if handler in self._global_handlers:
            self._global_handlers.remove(handler)
            return True
        return False

    async def emit(self, event: Event) -> None:
        """Emit an event to all subscribed handlers.

        Handlers are called in parallel. Errors are logged but don't
        prevent other handlers from executing.

        Args:
            event: Event to emit
        """
        event_type = str(event.type)
        handlers = self._handlers.get(event_type, []) + self._global_handlers

        if not handlers:
            logger.debug("event_no_handlers", event_type=event_type)
            return

        logger.debug(
            "event_emitting",
            event_type=event_type,
            handler_count=len(handlers),
            session_id=str(event.session_id),
            task_id=str(event.task_id),
        )

        results = await asyncio.gather(
            *[handler(event) for handler in handlers],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    "event_handler_error",
                    event_type=event_type,
                    error=str(result),
                    error_type=type(result).__name__,
                )

    def clear(self) -> None:
        """Remove all handlers. Useful for testing."""
        self._handlers.clear()
        self._global_handlers.clear()
