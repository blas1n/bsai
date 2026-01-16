"""Pydantic schemas for API request/response validation."""

from .memory import (
    ConsolidateResult,
    DecayResult,
    MemoryDetailResponse,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryStatsResponse,
)
from .requests import (
    BulkSessionAction,
    SessionCreate,
    SnapshotCreate,
    TaskCreate,
    TaskReject,
    TaskResume,
)
from .responses import (
    AgentStepResponse,
    ArtifactResponse,
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
    BreakpointCurrentState,
    BreakpointHitPayload,
    LLMChunkPayload,
    LLMCompletePayload,
    MilestoneProgressPayload,
    PreviousMilestoneInfo,
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
    "TaskResume",
    "TaskReject",
    "SnapshotCreate",
    "BulkSessionAction",
    # Responses
    "AgentStepResponse",
    "SessionResponse",
    "SessionDetailResponse",
    "TaskResponse",
    "TaskDetailResponse",
    "MilestoneResponse",
    "MilestoneDetailResponse",
    "SnapshotResponse",
    "ArtifactResponse",
    "PaginatedResponse",
    "ErrorResponse",
    # Memory
    "MemoryResponse",
    "MemoryDetailResponse",
    "MemorySearchResult",
    "MemorySearchRequest",
    "ConsolidateResult",
    "DecayResult",
    "MemoryStatsResponse",
    # WebSocket
    "WSMessageType",
    "WSMessage",
    "TaskStartedPayload",
    "TaskProgressPayload",
    "TaskCompletedPayload",
    "TaskFailedPayload",
    "MilestoneProgressPayload",
    "PreviousMilestoneInfo",
    "LLMChunkPayload",
    "LLMCompletePayload",
    "BreakpointCurrentState",
    "BreakpointHitPayload",
]
