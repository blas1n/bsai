"""Common utilities for MCP routers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from bsai.api.exceptions import NotFoundError
from bsai.db.models.mcp_server_config import McpServerConfig

from ...schemas.mcp import (
    McpServerDetailResponse,
    McpServerResponse,
    McpStdioConfig,
)

logger = structlog.get_logger()


@asynccontextmanager
async def connect_mcp_server(
    server: McpServerConfig,
    headers: dict[str, str] | None = None,
) -> AsyncIterator[ClientSession]:
    """Connect to MCP server using appropriate transport.

    Args:
        server: MCP server configuration
        headers: Optional auth headers

    Yields:
        Initialized ClientSession

    Raises:
        ValueError: If server URL is not configured
    """
    if not server.server_url:
        raise ValueError("Server URL is not configured")

    headers = headers or {}

    if server.transport_type == "sse":
        async with sse_client(url=server.server_url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:  # http
        async with streamable_http_client(url=server.server_url) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def list_mcp_tools_from_server(
    server: McpServerConfig,
    headers: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """List tools from MCP server.

    Args:
        server: MCP server configuration
        headers: Optional auth headers

    Returns:
        List of tool schemas
    """
    async with connect_mcp_server(server, headers) as session:
        tools_result = await session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or f"Tool: {tool.name}",
                "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
            }
            for tool in tools_result.tools
        ]


async def build_server_response(
    server: McpServerConfig, user_id: str, include_stdio_config: bool = False
) -> McpServerResponse | McpServerDetailResponse:
    """Build MCP server response from model.

    Args:
        server: McpServerConfig model instance
        user_id: Current user ID (for ownership verification)
        include_stdio_config: Whether to include stdio config (for native apps)

    Returns:
        Response model with appropriate fields
    """
    # Security: Only return server if user owns it
    if server.user_id != user_id:
        raise NotFoundError("MCP server", server.id)

    base_response = McpServerResponse(
        id=server.id,
        user_id=server.user_id,
        name=server.name,
        description=server.description,
        transport_type=server.transport_type,
        server_url=server.server_url,
        auth_type=server.auth_type,
        has_credentials=bool(server.auth_credentials),
        has_stdio_config=bool(server.command),
        available_tools=server.available_tools,
        require_approval=server.require_approval,
        enabled_for_worker=server.enabled_for_worker,
        enabled_for_qa=server.enabled_for_qa,
        is_active=server.is_active,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )

    if include_stdio_config and server.transport_type == "stdio" and server.command:
        return McpServerDetailResponse(
            **base_response.model_dump(),
            stdio_config=McpStdioConfig(
                command=server.command,
                args=server.args or [],
                env_vars=server.env_vars or {},
            ),
        )

    return base_response
