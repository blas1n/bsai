"""MCP utility functions shared across agents."""

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from agent.db.models.mcp_server_config import McpServerConfig
    from agent.db.repository.mcp_server_repo import McpServerRepository

logger = structlog.get_logger()


async def load_user_mcp_servers(
    mcp_server_repo: "McpServerRepository",
    user_id: str,
    agent_type: str,
) -> list["McpServerConfig"]:
    """Load enabled MCP servers for an agent.

    Args:
        mcp_server_repo: MCP server repository instance
        user_id: User ID to load servers for
        agent_type: Agent type ("worker" or "qa")

    Returns:
        List of enabled MCP server configurations
    """
    servers = await mcp_server_repo.get_enabled_for_agent(user_id, agent_type)

    logger.info(
        "mcp_servers_loaded",
        user_id=user_id,
        agent_type=agent_type,
        server_count=len(servers),
    )

    return servers
