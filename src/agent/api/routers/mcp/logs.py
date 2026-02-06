"""MCP execution logs endpoints."""

from uuid import UUID

from fastapi import APIRouter

from agent.db.repository.mcp_tool_log_repo import McpToolLogRepository

from ...dependencies import CurrentUserId, DBSession
from ...schemas.mcp import McpToolExecutionLogResponse
from ...schemas.responses import PaginatedResponse

router = APIRouter()


@router.get(
    "/logs",
    response_model=PaginatedResponse[McpToolExecutionLogResponse],
    summary="Get MCP tool execution logs",
)
async def get_mcp_logs(
    db: DBSession,
    user_id: CurrentUserId,
    session_id: UUID | None = None,
    status_filter: str | None = None,
    agent_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> PaginatedResponse[McpToolExecutionLogResponse]:
    """Get MCP tool execution logs for the current user.

    Args:
        db: Database session
        user_id: Current user ID
        session_id: Optional session filter
        status_filter: Optional status filter
        agent_type: Optional agent type filter
        limit: Maximum number of logs
        offset: Number of logs to skip

    Returns:
        Paginated list of tool execution logs
    """
    repo = McpToolLogRepository(db)

    if session_id:
        logs = await repo.get_by_session(session_id, limit, offset)
        total = await repo.count_by_session(session_id)
    else:
        logs = await repo.get_by_user(user_id, limit, offset, status_filter, agent_type)
        total = await repo.count_by_user(user_id, status_filter, agent_type)

    return PaginatedResponse(
        items=[McpToolExecutionLogResponse.model_validate(log) for log in logs],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(logs) < total,
    )
