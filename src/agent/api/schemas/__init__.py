"""Pydantic schemas for API request/response validation."""

from .requests import SessionCreate, SnapshotCreate, TaskCreate
from .responses import (
    ErrorResponse,
    MilestoneDetailResponse,
    MilestoneResponse,
    PaginatedResponse,
    SessionDetailResponse,
    SessionResponse,
    SnapshotResponse,
    TaskDetailResponse,
    TaskResponse,
)
from .websocket import (
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

__all__ = [
    # Requests
    "SessionCreate",
    "TaskCreate",
    "SnapshotCreate",
    # Responses
    "SessionResponse",
    "SessionDetailResponse",
    "TaskResponse",
    "TaskDetailResponse",
    "MilestoneResponse",
    "MilestoneDetailResponse",
    "SnapshotResponse",
    "PaginatedResponse",
    "ErrorResponse",
    # WebSocket
    "WSMessageType",
    "WSMessage",
    "TaskStartedPayload",
    "TaskProgressPayload",
    "TaskCompletedPayload",
    "TaskFailedPayload",
    "MilestoneProgressPayload",
    "LLMChunkPayload",
    "LLMCompletePayload",
]
