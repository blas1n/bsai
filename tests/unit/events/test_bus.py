"""Tests for EventBus implementation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from agent.events.bus import EventBus
from agent.events.types import (
    AgentActivityEvent,
    AgentStatus,
    Event,
    EventType,
    TaskCompletedEvent,
    TaskStartedEvent,
)


@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh EventBus for testing."""
    return EventBus()


@pytest.fixture
def sample_event() -> AgentActivityEvent:
    """Create a sample event for testing."""
    return AgentActivityEvent(
        type=EventType.AGENT_STARTED,
        session_id=uuid4(),
        task_id=uuid4(),
        milestone_id=uuid4(),
        sequence_number=1,
        agent="worker",
        status=AgentStatus.STARTED,
        message="Starting work",
    )


@pytest.fixture
def task_started_event() -> TaskStartedEvent:
    """Create a sample TaskStartedEvent."""
    return TaskStartedEvent(
        session_id=uuid4(),
        task_id=uuid4(),
        original_request="Test task",
        milestone_count=3,
    )


@pytest.fixture
def task_completed_event() -> TaskCompletedEvent:
    """Create a sample TaskCompletedEvent."""
    from decimal import Decimal

    return TaskCompletedEvent(
        session_id=uuid4(),
        task_id=uuid4(),
        final_result="Task completed successfully",
        total_input_tokens=1000,
        total_output_tokens=500,
        total_cost_usd=Decimal("0.05"),
        duration_seconds=30.5,
    )


class TestEventBusSubscribe:
    """Tests for EventBus.subscribe method."""

    async def test_subscribe_single_handler(
        self, event_bus: EventBus, sample_event: AgentActivityEvent
    ) -> None:
        """Test subscribing a single handler to an event type."""
        handler = AsyncMock()

        event_bus.subscribe(EventType.AGENT_STARTED, handler)
        await event_bus.emit(sample_event)

        handler.assert_called_once_with(sample_event)

    async def test_subscribe_multiple_handlers_same_type(
        self, event_bus: EventBus, sample_event: AgentActivityEvent
    ) -> None:
        """Test subscribing multiple handlers to the same event type."""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        event_bus.subscribe(EventType.AGENT_STARTED, handler1)
        event_bus.subscribe(EventType.AGENT_STARTED, handler2)
        await event_bus.emit(sample_event)

        handler1.assert_called_once_with(sample_event)
        handler2.assert_called_once_with(sample_event)

    async def test_subscribe_handler_different_types(self, event_bus: EventBus) -> None:
        """Test subscribing handlers to different event types."""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        event_bus.subscribe(EventType.AGENT_STARTED, handler1)
        event_bus.subscribe(EventType.AGENT_COMPLETED, handler2)

        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.STARTED,
            message="Starting",
        )

        await event_bus.emit(event)

        handler1.assert_called_once()
        handler2.assert_not_called()

    async def test_subscribe_with_string_event_type(
        self, event_bus: EventBus, sample_event: AgentActivityEvent
    ) -> None:
        """Test subscribing with string event type."""
        handler = AsyncMock()

        event_bus.subscribe("agent.started", handler)
        await event_bus.emit(sample_event)

        handler.assert_called_once_with(sample_event)


class TestEventBusSubscribeAll:
    """Tests for EventBus.subscribe_all method."""

    async def test_subscribe_all_receives_all_events(self, event_bus: EventBus) -> None:
        """Test that global handler receives all event types."""
        handler = AsyncMock()
        event_bus.subscribe_all(handler)

        event1 = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.STARTED,
            message="Starting",
        )

        event2 = AgentActivityEvent(
            type=EventType.AGENT_COMPLETED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.COMPLETED,
            message="Done",
        )

        await event_bus.emit(event1)
        await event_bus.emit(event2)

        assert handler.call_count == 2

    async def test_subscribe_all_with_specific_handlers(
        self, event_bus: EventBus, sample_event: AgentActivityEvent
    ) -> None:
        """Test global handler works alongside specific handlers."""
        global_handler = AsyncMock()
        specific_handler = AsyncMock()

        event_bus.subscribe_all(global_handler)
        event_bus.subscribe(EventType.AGENT_STARTED, specific_handler)

        await event_bus.emit(sample_event)

        global_handler.assert_called_once_with(sample_event)
        specific_handler.assert_called_once_with(sample_event)


class TestEventBusUnsubscribe:
    """Tests for EventBus.unsubscribe methods."""

    async def test_unsubscribe_removes_handler(
        self, event_bus: EventBus, sample_event: AgentActivityEvent
    ) -> None:
        """Test unsubscribing removes the handler."""
        handler = AsyncMock()

        event_bus.subscribe(EventType.AGENT_STARTED, handler)
        result = event_bus.unsubscribe(EventType.AGENT_STARTED, handler)

        assert result is True

        await event_bus.emit(sample_event)
        handler.assert_not_called()

    async def test_unsubscribe_nonexistent_handler(self, event_bus: EventBus) -> None:
        """Test unsubscribing a non-existent handler returns False."""
        handler = AsyncMock()

        result = event_bus.unsubscribe(EventType.AGENT_STARTED, handler)

        assert result is False

    async def test_unsubscribe_all_removes_global_handler(
        self, event_bus: EventBus, sample_event: AgentActivityEvent
    ) -> None:
        """Test unsubscribing from global handlers."""
        handler = AsyncMock()

        event_bus.subscribe_all(handler)
        result = event_bus.unsubscribe_all(handler)

        assert result is True

        await event_bus.emit(sample_event)
        handler.assert_not_called()

    async def test_unsubscribe_all_nonexistent_handler(self, event_bus: EventBus) -> None:
        """Test unsubscribing a non-existent global handler."""
        handler = AsyncMock()

        result = event_bus.unsubscribe_all(handler)

        assert result is False


class TestEventBusEmit:
    """Tests for EventBus.emit method."""

    async def test_emit_no_handlers(self, event_bus: EventBus) -> None:
        """Test emitting event with no handlers doesn't raise."""
        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.STARTED,
            message="Starting",
        )

        # Should not raise
        await event_bus.emit(event)

    async def test_emit_parallel_execution(self, event_bus: EventBus) -> None:
        """Test that handlers are executed in parallel."""
        call_order = []

        async def slow_handler(event: Event) -> None:
            call_order.append("slow_start")
            await asyncio.sleep(0.1)
            call_order.append("slow_end")

        async def fast_handler(event: Event) -> None:
            call_order.append("fast_start")
            call_order.append("fast_end")

        event_bus.subscribe(EventType.AGENT_STARTED, slow_handler)
        event_bus.subscribe(EventType.AGENT_STARTED, fast_handler)

        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.STARTED,
            message="Starting",
        )

        await event_bus.emit(event)

        # Both handlers started before slow_handler finished
        call_order.index("slow_start")
        call_order.index("fast_start")
        slow_end_idx = call_order.index("slow_end")

        # Fast handler should complete before slow handler
        assert call_order.index("fast_end") < slow_end_idx

    async def test_emit_handler_error_isolation(self, event_bus: EventBus) -> None:
        """Test that one handler's error doesn't affect others."""
        successful_handler = AsyncMock()

        async def failing_handler(event: Event) -> None:
            raise ValueError("Handler failed")

        event_bus.subscribe(EventType.AGENT_STARTED, failing_handler)
        event_bus.subscribe(EventType.AGENT_STARTED, successful_handler)

        event = AgentActivityEvent(
            type=EventType.AGENT_STARTED,
            session_id=uuid4(),
            task_id=uuid4(),
            milestone_id=uuid4(),
            sequence_number=1,
            agent="worker",
            status=AgentStatus.STARTED,
            message="Starting",
        )

        # Should not raise
        await event_bus.emit(event)

        # Successful handler should still be called
        successful_handler.assert_called_once_with(event)


class TestEventBusClear:
    """Tests for EventBus.clear method."""

    async def test_clear_removes_all_handlers(
        self, event_bus: EventBus, sample_event: AgentActivityEvent
    ) -> None:
        """Test that clear removes all handlers."""
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        global_handler = AsyncMock()

        event_bus.subscribe(EventType.AGENT_STARTED, handler1)
        event_bus.subscribe(EventType.AGENT_COMPLETED, handler2)
        event_bus.subscribe_all(global_handler)

        event_bus.clear()

        await event_bus.emit(sample_event)

        handler1.assert_not_called()
        handler2.assert_not_called()
        global_handler.assert_not_called()


class TestEventBusConstruction:
    """Tests for EventBus construction."""

    def test_new_instances_are_independent(self) -> None:
        """Test that each EventBus() call creates an independent instance."""
        bus1 = EventBus()
        bus2 = EventBus()

        assert isinstance(bus1, EventBus)
        assert isinstance(bus2, EventBus)
        assert bus1 is not bus2

    def test_new_bus_has_no_handlers(self) -> None:
        """Test that newly created EventBus has no handlers."""
        bus = EventBus()

        assert len(bus._handlers) == 0
        assert len(bus._global_handlers) == 0
