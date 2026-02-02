"""MCP router module.

This module organizes MCP endpoints into focused sub-routers:
- servers: Server CRUD operations
- tools: Tool testing and listing
- oauth: OAuth authentication flow
- logs: Execution logs

The combined router is exported for use in the main app.
"""

from fastapi import APIRouter

# Import utilities for re-export
from ._common import build_server_response, connect_mcp_server, list_mcp_tools_from_server

# Import sub-routers
from .logs import router as logs_router
from .oauth import (
    _build_wellknown_url,
    _discover_oauth_metadata,
    _initiate_oauth_flow,
    _register_oauth_client,
    oauth_callback,
)
from .oauth import router as oauth_router
from .servers import router as servers_router
from .tools import router as tools_router

# Combined router with all MCP endpoints
router = APIRouter(prefix="/mcp", tags=["mcp"])

# Include all sub-routers
router.include_router(servers_router)
router.include_router(tools_router)
router.include_router(logs_router)
router.include_router(oauth_router)

# Backward compatibility alias
_build_server_response = build_server_response

__all__ = [
    "router",
    "connect_mcp_server",
    "list_mcp_tools_from_server",
    "build_server_response",
    "_build_server_response",
    "_build_wellknown_url",
    "_discover_oauth_metadata",
    "_initiate_oauth_flow",
    "_register_oauth_client",
    "oauth_callback",
]
