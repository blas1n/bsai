"""Event-driven architecture for agent workflow.

This module provides an EventBus for decoupling business logic from
notification/persistence concerns. Nodes emit events, handlers process them.
"""

from .bus import EventBus
from .types import (
    AgentActivityEvent,
    AgentStatus,
    BreakpointHitEvent,
    BreakpointResumedEvent,
    ContextCompressedEvent,
    Event,
    EventType,
    LLMChunkEvent,
    LLMCompleteEvent,
    MilestoneRetryEvent,
    MilestoneStatus,
    MilestoneStatusChangedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskProgressEvent,
    TaskStartedEvent,
)

__all__ = [
    # Bus
    "EventBus",
    # Types
    "AgentActivityEvent",
    "AgentStatus",
    "BreakpointHitEvent",
    "BreakpointResumedEvent",
    "ContextCompressedEvent",
    "Event",
    "EventType",
    "LLMChunkEvent",
    "LLMCompleteEvent",
    "MilestoneRetryEvent",
    "MilestoneStatus",
    "MilestoneStatusChangedEvent",
    "TaskCompletedEvent",
    "TaskFailedEvent",
    "TaskProgressEvent",
    "TaskStartedEvent",
]
