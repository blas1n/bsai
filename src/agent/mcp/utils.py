"""MCP utility functions shared across agents."""

from __future__ import annotations

import traceback
from typing import Any

import httpx
import structlog
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from agent.db.models.mcp_server_config import McpServerConfig
from agent.db.repository.mcp_server_repo import McpServerRepository
from agent.mcp.security import build_mcp_auth_headers

logger = structlog.get_logger()


async def load_user_mcp_servers(
    mcp_server_repo: McpServerRepository,
    user_id: str,
    agent_type: str,
) -> list[McpServerConfig]:
    """Load enabled MCP servers for an agent.

    Args:
        mcp_server_repo: MCP server repository instance
        user_id: User ID to load servers for
        agent_type: Agent type ("worker" or "qa")

    Returns:
        List of enabled MCP server configurations
    """
    servers = await mcp_server_repo.get_enabled_for_agent(user_id, agent_type)

    # Debug: Log server details for troubleshooting
    if servers:
        server_names = [s.name for s in servers]
        logger.info(
            "mcp_servers_loaded",
            user_id=user_id,
            agent_type=agent_type,
            server_count=len(servers),
            server_names=server_names,
        )
    else:
        # Log at warning level when no servers found to help debug
        logger.warning(
            "mcp_no_servers_found",
            user_id=user_id,
            agent_type=agent_type,
            hint="Check if MCP servers exist with is_active=True and enabled_for_worker=True",
        )

    return servers


async def load_tools_from_mcp_server(
    server: McpServerConfig,
) -> list[dict[str, Any]]:
    """Load tool schemas from an MCP server.

    Connects to the MCP server and fetches available tools with their schemas.

    Args:
        server: MCP server configuration

    Returns:
        List of tool schema dictionaries with name, description, inputSchema
    """
    if server.transport_type == "stdio":
        # stdio servers cannot be accessed from backend
        logger.debug("mcp_skip_stdio_server", server_name=server.name)
        return []

    if not server.server_url:
        logger.warning("mcp_server_no_url", server_name=server.name)
        return []

    # Build auth headers if configured
    headers = build_mcp_auth_headers(server)

    # Check if auth is required but headers are missing
    if server.auth_type and server.auth_type != "none" and not headers:
        logger.warning(
            "mcp_auth_required_but_missing",
            server_name=server.name,
            auth_type=server.auth_type,
        )
        return []

    try:
        tools: list[dict[str, Any]] = []

        if server.transport_type == "sse":
            async with sse_client(url=server.server_url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    for tool in tools_result.tools:
                        tools.append(
                            {
                                "name": tool.name,
                                "description": tool.description or "",
                                "inputSchema": tool.inputSchema if tool.inputSchema else {},
                            }
                        )
        else:  # http
            # Create httpx client with headers for authentication
            http_client = httpx.AsyncClient(headers=headers) if headers else None
            async with streamable_http_client(url=server.server_url, http_client=http_client) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    for tool in tools_result.tools:
                        tools.append(
                            {
                                "name": tool.name,
                                "description": tool.description or "",
                                "inputSchema": tool.inputSchema if tool.inputSchema else {},
                            }
                        )

        # Filter by available_tools if configured (it's a list of tool names)
        if server.available_tools:
            allowed_names = set(server.available_tools)
            tools = [t for t in tools if t["name"] in allowed_names]

        logger.info(
            "mcp_tools_loaded",
            server_name=server.name,
            tool_count=len(tools),
        )

        return tools

    except Exception as e:
        logger.warning(
            "mcp_tools_load_failed",
            server_name=server.name,
            server_url=server.server_url,
            transport_type=server.transport_type,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        return []


async def load_all_mcp_tools(
    servers: list[McpServerConfig],
) -> dict[str, list[dict[str, Any]]]:
    """Load tools from all MCP servers.

    Args:
        servers: List of MCP server configurations

    Returns:
        Dictionary mapping server name to list of tool schemas
    """
    result: dict[str, list[dict[str, Any]]] = {}

    for server in servers:
        tools = await load_tools_from_mcp_server(server)
        if tools:
            result[server.name] = tools

    total_tools = sum(len(t) for t in result.values())
    logger.info(
        "mcp_all_tools_loaded",
        server_count=len(result),
        total_tool_count=total_tools,
    )

    return result
