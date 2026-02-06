"""MCP tools endpoints."""

import time
from uuid import UUID

from fastapi import APIRouter

from bsai.api.config import get_mcp_settings
from bsai.api.exceptions import NotFoundError, ValidationError
from bsai.db.repository.mcp_server_repo import McpServerRepository
from bsai.mcp.security import build_mcp_auth_headers

from ...dependencies import CurrentUserId, DBSession
from ...schemas.mcp import McpServerTestResponse, McpToolSchema
from ._common import connect_mcp_server

router = APIRouter()


@router.post(
    "/servers/{server_id}/test",
    response_model=McpServerTestResponse,
    summary="Test MCP server connection",
)
async def test_mcp_server(
    server_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
) -> McpServerTestResponse:
    """Test connection to MCP server (HTTP/SSE only).

    stdio servers cannot be tested from backend.
    """
    repo = McpServerRepository(db)
    server = await repo.get_by_id_and_user(server_id, user_id)

    if not server:
        raise NotFoundError("MCP server", server_id)

    if server.transport_type == "stdio":
        raise ValidationError(
            "stdio servers cannot be tested from backend. Use native app to test."
        )

    # Build auth headers if configured
    settings = get_mcp_settings()
    headers = build_mcp_auth_headers(server, settings)

    # Check if auth is required but headers are missing
    if server.auth_type and server.auth_type != "none" and not headers:
        return McpServerTestResponse(
            success=False,
            error="Authentication credentials are not configured or could not be decrypted. "
            "Please update your authentication settings.",
            available_tools=None,
            latency_ms=None,
        )

    try:
        start_time = time.monotonic()
        async with connect_mcp_server(server, headers) as session:
            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]

        latency_ms = int((time.monotonic() - start_time) * 1000)

        return McpServerTestResponse(
            success=True,
            error=None,
            available_tools=tool_names,
            latency_ms=latency_ms,
        )

    except Exception as e:
        return McpServerTestResponse(
            success=False,
            error=f"{type(e).__name__}: {e}",
            available_tools=None,
            latency_ms=None,
        )


@router.get(
    "/servers/{server_id}/tools",
    response_model=list[McpToolSchema],
    summary="List available MCP tools",
)
async def list_mcp_tools(
    server_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
) -> list[McpToolSchema]:
    """List available tools from MCP server.

    For stdio servers, returns empty list (tools must be discovered by native app).
    """
    repo = McpServerRepository(db)
    server = await repo.get_by_id_and_user(server_id, user_id)

    if not server:
        raise NotFoundError("MCP server", server_id)

    # stdio servers can't be connected from backend
    if server.transport_type == "stdio":
        return []

    # Build auth headers if configured
    settings = get_mcp_settings()
    headers = build_mcp_auth_headers(server, settings)

    try:
        async with connect_mcp_server(server, headers) as session:
            tools_result = await session.list_tools()
            return [
                McpToolSchema(
                    name=tool.name,
                    description=tool.description or f"Tool: {tool.name}",
                    input_schema=tool.inputSchema if hasattr(tool, "inputSchema") else {},
                )
                for tool in tools_result.tools
            ]
    except Exception:
        # Return empty list on connection failure
        return []
