"""MCP (Model Context Protocol) server management endpoints."""

import base64
import hashlib
import json
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, status
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from agent.api.config import get_mcp_settings
from agent.api.exceptions import ConflictError, NotFoundError, ValidationError
from agent.cache.redis_client import get_redis
from agent.db.models.mcp_server_config import McpServerConfig
from agent.db.repository.mcp_server_repo import McpServerRepository
from agent.db.repository.mcp_tool_log_repo import McpToolLogRepository
from agent.mcp.security import (
    CredentialEncryption,
    McpSecurityValidator,
    build_mcp_auth_headers,
)

from ..dependencies import CurrentUserId, DBSession
from ..schemas.mcp import (
    McpOAuthCallbackRequest,
    McpOAuthCallbackResponse,
    McpOAuthStartRequest,
    McpOAuthStartResponse,
    McpServerCreateRequest,
    McpServerDetailResponse,
    McpServerResponse,
    McpServerTestResponse,
    McpServerUpdateRequest,
    McpStdioConfig,
    McpToolExecutionLogResponse,
    McpToolSchema,
    PaginatedResponse,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/mcp", tags=["mcp"])


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


async def _build_server_response(
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


@router.get(
    "/servers",
    response_model=list[McpServerResponse],
    summary="List MCP servers",
)
async def list_mcp_servers(
    db: DBSession,
    user_id: CurrentUserId,
    is_active_only: bool = True,
) -> list[McpServerResponse]:
    """Get all MCP servers for the current user.

    Args:
        db: Database session
        user_id: Current user ID
        is_active_only: Only return active servers

    Returns:
        List of MCP server configurations
    """
    repo = McpServerRepository(db)
    servers = await repo.get_by_user(user_id, is_active_only=is_active_only)
    return [await _build_server_response(s, user_id) for s in servers]


@router.get(
    "/servers/{server_id}",
    response_model=McpServerDetailResponse,
    summary="Get MCP server details",
)
async def get_mcp_server(
    server_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
    include_stdio_config: bool = True,
) -> McpServerResponse | McpServerDetailResponse:
    """Get detailed MCP server configuration.

    Args:
        server_id: Server UUID
        db: Database session
        user_id: Current user ID
        include_stdio_config: Include stdio config for native apps

    Returns:
        Detailed MCP server configuration
    """
    repo = McpServerRepository(db)
    server = await repo.get_by_id_and_user(server_id, user_id)

    if not server:
        raise NotFoundError("MCP server", server_id)

    return await _build_server_response(server, user_id, include_stdio_config)


@router.post(
    "/servers",
    response_model=McpServerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create MCP server",
)
async def create_mcp_server(
    request: McpServerCreateRequest,
    db: DBSession,
    user_id: CurrentUserId,
) -> McpServerResponse:
    """Create a new MCP server configuration.

    Args:
        request: MCP server creation request
        db: Database session
        user_id: Current user ID

    Returns:
        Created MCP server configuration
    """
    repo = McpServerRepository(db)
    settings = get_mcp_settings()
    validator = McpSecurityValidator(settings)
    encryptor = CredentialEncryption(settings)

    # Check for duplicate name
    existing = await repo.get_by_name_and_user(request.name, user_id)
    if existing:
        raise ConflictError("MCP server", request.name)

    # Validate based on transport type
    if request.transport_type in ["http", "sse"]:
        if not request.server_url:
            raise ValidationError(
                f"server_url is required for {request.transport_type} transport",
            )
        # Validate URL for SSRF
        try:
            validator.validate_server_url(request.server_url)
        except ValueError as e:
            raise ValidationError(str(e)) from e

    elif request.transport_type == "stdio":
        if not request.command:
            raise ValidationError("command is required for stdio transport")
        # Validate command against allowlist
        try:
            validator.validate_stdio_command(request.command)
        except ValueError as e:
            raise ValidationError(str(e)) from e

    # Encrypt credentials if provided
    encrypted_credentials = None
    if request.auth_credentials:
        try:
            encrypted_credentials = encryptor.encrypt(request.auth_credentials)
        except ValueError as e:
            raise ValidationError(f"Failed to encrypt credentials: {e}") from e

    # Create server
    server = await repo.create(
        user_id=user_id,
        name=request.name,
        description=request.description,
        transport_type=request.transport_type,
        server_url=request.server_url,
        auth_type=request.auth_type,
        auth_credentials=encrypted_credentials,
        command=request.command,
        args=request.args,
        env_vars=request.env_vars,
        available_tools=request.available_tools,
        require_approval=request.require_approval,
        enabled_for_worker=request.enabled_for_worker,
        enabled_for_qa=request.enabled_for_qa,
    )

    await db.commit()
    return await _build_server_response(server, user_id)


@router.patch(
    "/servers/{server_id}",
    response_model=McpServerResponse,
    summary="Update MCP server",
)
async def update_mcp_server(
    server_id: UUID,
    request: McpServerUpdateRequest,
    db: DBSession,
    user_id: CurrentUserId,
) -> McpServerResponse:
    """Update MCP server configuration.

    Args:
        server_id: Server UUID
        request: Update request
        db: Database session
        user_id: Current user ID

    Returns:
        Updated MCP server configuration
    """
    repo = McpServerRepository(db)
    settings = get_mcp_settings()
    validator = McpSecurityValidator(settings)
    encryptor = CredentialEncryption(settings)

    # Prepare update data
    update_data: dict[str, Any] = {}

    if request.name is not None:
        # Check for duplicate name
        existing = await repo.get_by_name_and_user(request.name, user_id)
        if existing and existing.id != server_id:
            raise ConflictError("MCP server", request.name)
        update_data["name"] = request.name

    if request.description is not None:
        update_data["description"] = request.description

    if request.is_active is not None:
        update_data["is_active"] = request.is_active

    # HTTP/SSE updates
    if request.server_url is not None:
        try:
            validator.validate_server_url(request.server_url)
        except ValueError as e:
            raise ValidationError(str(e)) from e
        update_data["server_url"] = request.server_url

    if request.auth_type is not None:
        update_data["auth_type"] = request.auth_type

    if request.auth_credentials is not None:
        try:
            update_data["auth_credentials"] = encryptor.encrypt(request.auth_credentials)
        except ValueError as e:
            raise ValidationError(f"Failed to encrypt credentials: {e}") from e

    # stdio updates
    if request.command is not None:
        try:
            validator.validate_stdio_command(request.command)
        except ValueError as e:
            raise ValidationError(str(e)) from e
        update_data["command"] = request.command

    if request.args is not None:
        update_data["args"] = request.args

    if request.env_vars is not None:
        update_data["env_vars"] = request.env_vars

    # Configuration updates
    if request.available_tools is not None:
        update_data["available_tools"] = request.available_tools

    if request.require_approval is not None:
        update_data["require_approval"] = request.require_approval

    if request.enabled_for_worker is not None:
        update_data["enabled_for_worker"] = request.enabled_for_worker

    if request.enabled_for_qa is not None:
        update_data["enabled_for_qa"] = request.enabled_for_qa

    # Update server
    server = await repo.update_by_user(server_id, user_id, **update_data)

    if not server:
        raise NotFoundError("MCP server", server_id)

    await db.commit()
    return await _build_server_response(server, user_id)


@router.delete(
    "/servers/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete MCP server",
)
async def delete_mcp_server(
    server_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
) -> None:
    """Soft delete MCP server configuration.

    Args:
        server_id: Server UUID
        db: Database session
        user_id: Current user ID
    """
    repo = McpServerRepository(db)
    success = await repo.delete_by_user(server_id, user_id)

    if not success:
        raise NotFoundError("MCP server", server_id)

    await db.commit()


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

    Args:
        server_id: Server UUID
        db: Database session
        user_id: Current user ID

    Returns:
        Test result with connection status
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
        # Measure latency and load tools using helper
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
    """Get available tools from MCP server.

    Args:
        server_id: Server UUID
        db: Database session
        user_id: Current user ID

    Returns:
        List of available tools
    """
    repo = McpServerRepository(db)
    server = await repo.get_by_id_and_user(server_id, user_id)

    if not server:
        raise NotFoundError("MCP server", server_id)

    # stdio servers cannot list tools from backend
    if server.transport_type == "stdio":
        # Return cached tools if available
        if server.available_tools:
            return [
                McpToolSchema(
                    name=tool_name,
                    description=f"Tool: {tool_name}",
                    input_schema={},
                )
                for tool_name in server.available_tools
            ]
        return []

    try:
        # Build auth headers if configured
        headers = build_mcp_auth_headers(server)

        # Load tools using helper
        async with connect_mcp_server(server, headers) as session:
            tools_result = await session.list_tools()

        result = [
            McpToolSchema(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema if tool.inputSchema else {},
            )
            for tool in tools_result.tools
        ]

        # Filter by available_tools if configured
        if server.available_tools:
            allowed_tools = set(server.available_tools)
            result = [t for t in result if t.name in allowed_tools]

        return result

    except Exception:
        # Return cached tools if MCP connection fails
        if server.available_tools:
            return [
                McpToolSchema(
                    name=tool_name,
                    description=f"Tool: {tool_name}",
                    input_schema={},
                )
                for tool_name in server.available_tools
            ]
        return []


@router.get(
    "/logs",
    response_model=PaginatedResponse,
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
) -> PaginatedResponse:
    """Get tool execution logs for the current user.

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
    log_repo = McpToolLogRepository(db)

    if session_id:
        logs = await log_repo.get_by_session(session_id, limit, offset)
        total = await log_repo.count_by_session(session_id)
    else:
        logs = await log_repo.get_by_user(user_id, limit, offset, status_filter, agent_type)
        total = await log_repo.count_by_user(user_id, status_filter, agent_type)

    # Convert to response models
    items = [McpToolExecutionLogResponse.model_validate(log) for log in logs]

    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(logs) < total,
    )


# OAuth2 Flow Endpoints

OAUTH_STATE_PREFIX = "mcp_oauth_state:"
OAUTH_STATE_TTL = 600  # 10 minutes


def _build_wellknown_url(base_url: str, wellknown_path: str) -> str:
    """Build well-known URL safely from validated base URL.

    Only appends well-known paths to the already-validated base URL.
    This prevents SSRF by ensuring we only request from the same origin.

    Args:
        base_url: Already-validated base URL
        wellknown_path: Well-known path (must start with /.well-known/)

    Returns:
        Full well-known URL

    Raises:
        ValueError: If wellknown_path is not a valid well-known path
    """
    # Only allow specific well-known paths
    allowed_paths = {
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
    }
    if wellknown_path not in allowed_paths:
        raise ValueError(f"Invalid well-known path: {wellknown_path}")

    return urljoin(base_url, wellknown_path)


async def _discover_oauth_metadata(server_url: str) -> dict[str, Any] | None:
    """Discover OAuth metadata from MCP server.

    Tries standard OAuth discovery endpoints.

    Args:
        server_url: MCP server URL

    Returns:
        OAuth metadata dict or None if not found

    Raises:
        ValueError: If URL fails SSRF validation
    """
    # Validate URL to prevent SSRF attacks
    settings = get_mcp_settings()
    validator = McpSecurityValidator(settings)
    validator.validate_server_url(server_url)

    # Normalize to origin-only URL (scheme + host[:port]) to avoid using any
    # user-controlled path/query/fragment when building well-known URLs.
    parsed = urlparse(server_url)
    normalized_base_url = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Try protected resource metadata first (RFC 9728)
        try:
            protected_resource_url = _build_wellknown_url(
                normalized_base_url, "/.well-known/oauth-protected-resource"
            )
            response = await client.get(protected_resource_url)
            if response.status_code == 200:
                resource_meta = response.json()
                # Get authorization server URL
                auth_server = resource_meta.get("authorization_servers", [None])[0]
                if auth_server:
                    # Validate auth server URL before making request
                    validator.validate_server_url(auth_server)
                    # Build well-known URL from validated auth server
                    auth_server_meta_url = _build_wellknown_url(
                        auth_server, "/.well-known/oauth-authorization-server"
                    )
                    # Fetch authorization server metadata
                    meta_response = await client.get(auth_server_meta_url)
                    if meta_response.status_code == 200:
                        meta_result: dict[str, Any] = meta_response.json()
                        return meta_result
        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.debug(
                "oauth_protected_resource_discovery_failed", server_url=server_url, error=str(e)
            )

        # Try standard OAuth metadata discovery (RFC 8414)
        try:
            oauth_server_url = _build_wellknown_url(
                server_url, "/.well-known/oauth-authorization-server"
            )
            response = await client.get(oauth_server_url)
            if response.status_code == 200:
                standard_result: dict[str, Any] = response.json()
                return standard_result
        except Exception as e:
            logger.debug(
                "oauth_authorization_server_discovery_failed", server_url=server_url, error=str(e)
            )

        # Try OpenID Connect discovery
        try:
            openid_url = _build_wellknown_url(server_url, "/.well-known/openid-configuration")
            response = await client.get(openid_url)
            if response.status_code == 200:
                openid_result: dict[str, Any] = response.json()
                return openid_result
        except Exception as e:
            logger.debug(
                "openid_configuration_discovery_failed", server_url=server_url, error=str(e)
            )

    return None


async def _register_oauth_client(
    registration_endpoint: str,
    redirect_uri: str,
    client_name: str = "BSAI MCP Client",
) -> dict[str, Any] | None:
    """Dynamically register an OAuth client (RFC 7591).

    Args:
        registration_endpoint: OAuth registration endpoint URL
        redirect_uri: Redirect URI for the client
        client_name: Name for the client

    Returns:
        Client registration response with client_id and client_secret, or None

    Raises:
        ValueError: If registration endpoint fails SSRF validation
    """
    # Validate registration endpoint URL to prevent SSRF attacks
    settings = get_mcp_settings()
    validator = McpSecurityValidator(settings)
    validator.validate_server_url(registration_endpoint)

    registration_request = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",  # Public client
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                registration_endpoint,
                json=registration_request,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code in (200, 201):
                result: dict[str, Any] = response.json()
                return result
        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.debug(
                "oauth_client_registration_failed", endpoint=registration_endpoint, error=str(e)
            )

    return None


async def _initiate_oauth_flow(
    server_url: str,
    callback_url: str,
    user_id: str,
    extra_state_data: dict[str, Any] | None = None,
) -> McpOAuthStartResponse:
    """Common OAuth flow initiation logic.

    Discovers OAuth metadata, registers client if needed, generates PKCE parameters,
    stores state in Redis, and returns authorization URL.

    Args:
        server_url: MCP server URL for OAuth discovery
        callback_url: URL to redirect after OAuth completion
        user_id: Current user ID
        extra_state_data: Additional data to store in OAuth state (e.g., server_id)

    Returns:
        OAuth start response with authorization URL and state

    Raises:
        ValidationError: If OAuth discovery or setup fails
    """
    # Discover OAuth metadata
    try:
        metadata = await _discover_oauth_metadata(server_url)
    except Exception as e:
        raise ValidationError(
            f"Failed to discover OAuth configuration: {type(e).__name__} - {e}"
        ) from e

    if not metadata:
        raise ValidationError(
            f"Could not discover OAuth configuration for {server_url}. "
            "The server may not support OAuth2 authentication."
        )

    auth_endpoint = metadata.get("authorization_endpoint")
    if not auth_endpoint:
        raise ValidationError("OAuth metadata missing authorization_endpoint")

    # Validate authorization endpoint URL to prevent SSRF
    settings = get_mcp_settings()
    validator = McpSecurityValidator(settings)
    try:
        validator.validate_server_url(auth_endpoint)
    except ValueError as e:
        raise ValidationError(f"Invalid authorization endpoint URL: {e}") from e

    # Dynamic client registration if registration_endpoint is available
    client_id = metadata.get("client_id")
    client_secret = None
    registration_endpoint = metadata.get("registration_endpoint")

    if not client_id and registration_endpoint:
        # Validate registration endpoint URL
        try:
            validator.validate_server_url(registration_endpoint)
        except ValueError as e:
            raise ValidationError(f"Invalid registration endpoint URL: {e}") from e

        client_info = await _register_oauth_client(
            registration_endpoint,
            callback_url,
        )
        if client_info:
            client_id = client_info.get("client_id")
            client_secret = client_info.get("client_secret")

    if not client_id:
        raise ValidationError(
            "OAuth server requires client registration but dynamic registration failed. "
            "Please register a client manually with the OAuth provider."
        )

    # Generate PKCE parameters
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )

    # Generate state
    state = secrets.token_urlsafe(32)

    # Store OAuth state in Redis
    try:
        redis_client = get_redis().client
        oauth_data = {
            "user_id": user_id,
            "server_url": server_url,
            "callback_url": callback_url,
            "code_verifier": code_verifier,
            "client_id": client_id,
            "client_secret": client_secret,
            "metadata": metadata,
        }
        # Merge extra state data if provided
        if extra_state_data:
            oauth_data.update(extra_state_data)

        await redis_client.setex(
            f"{OAUTH_STATE_PREFIX}{state}",
            OAUTH_STATE_TTL,
            json.dumps(oauth_data),
        )
    except Exception as e:
        raise ValidationError(f"Failed to store OAuth state: {type(e).__name__} - {e}") from e

    # Build authorization URL
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": callback_url,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    if "scopes_supported" in metadata:
        auth_params["scope"] = " ".join(metadata["scopes_supported"][:5])

    authorization_url = f"{auth_endpoint}?{urlencode(auth_params)}"

    return McpOAuthStartResponse(
        authorization_url=authorization_url,
        state=state,
    )


@router.post(
    "/oauth/start",
    response_model=McpOAuthStartResponse,
    summary="Start OAuth flow for MCP server",
)
async def start_oauth_flow(
    request: McpOAuthStartRequest,
    user_id: CurrentUserId,
) -> McpOAuthStartResponse:
    """Start OAuth authorization flow for an MCP server.

    Discovers OAuth endpoints and returns authorization URL.

    Args:
        request: OAuth start request with server URL
        user_id: Current user ID

    Returns:
        Authorization URL and state parameter
    """
    return await _initiate_oauth_flow(
        server_url=request.server_url,
        callback_url=request.callback_url,
        user_id=user_id,
    )


@router.post(
    "/oauth/callback",
    response_model=McpOAuthCallbackResponse,
    summary="Complete OAuth flow with authorization code",
)
async def oauth_callback(
    request: McpOAuthCallbackRequest,
    db: DBSession,
    user_id: CurrentUserId,
) -> McpOAuthCallbackResponse:
    """Complete OAuth flow by exchanging authorization code for tokens.

    Args:
        request: Callback request with code and state
        db: Database session
        user_id: Current user ID

    Returns:
        Success/failure response
    """
    redis_client = get_redis().client
    settings = get_mcp_settings()
    encryptor = CredentialEncryption(settings)

    # Verify state and get stored OAuth data
    state_key = f"{OAUTH_STATE_PREFIX}{request.state}"
    oauth_data_str = await redis_client.get(state_key)

    if not oauth_data_str:
        return McpOAuthCallbackResponse(
            success=False,
            error="Invalid or expired OAuth state. Please try again.",
        )

    # Parse stored data
    try:
        oauth_data = json.loads(oauth_data_str)
    except json.JSONDecodeError:
        return McpOAuthCallbackResponse(
            success=False,
            error="Corrupted OAuth state data.",
        )

    # Verify user
    if oauth_data.get("user_id") != user_id:
        return McpOAuthCallbackResponse(
            success=False,
            error="OAuth state does not match current user.",
        )

    # Delete state (one-time use)
    await redis_client.delete(state_key)

    # Get token endpoint
    metadata = oauth_data.get("metadata", {})
    token_endpoint = metadata.get("token_endpoint")

    if not token_endpoint:
        return McpOAuthCallbackResponse(
            success=False,
            error="OAuth metadata missing token_endpoint",
        )

    # Validate token endpoint URL to prevent SSRF attacks
    settings = get_mcp_settings()
    validator = McpSecurityValidator(settings)
    try:
        validator.validate_server_url(token_endpoint)
    except ValueError as e:
        return McpOAuthCallbackResponse(
            success=False,
            error=f"Invalid token endpoint URL: {e}",
        )

    # Exchange code for tokens - use registered client_id from oauth_data
    client_id = oauth_data.get("client_id")
    client_secret = oauth_data.get("client_secret")

    if not client_id:
        return McpOAuthCallbackResponse(
            success=False,
            error="Missing client_id in OAuth state",
        )

    token_data = {
        "grant_type": "authorization_code",
        "code": request.code,
        "redirect_uri": oauth_data.get("callback_url"),
        "client_id": client_id,
        "code_verifier": oauth_data.get("code_verifier"),
    }

    # Add client_secret if available (for confidential clients)
    if client_secret:
        token_data["client_secret"] = client_secret

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                token_endpoint,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_detail = response.text[:200] if response.text else "Unknown error"
                return McpOAuthCallbackResponse(
                    success=False,
                    error=f"Token exchange failed: {error_detail}",
                )

            tokens = response.json()

    except Exception as e:
        return McpOAuthCallbackResponse(
            success=False,
            error=f"Failed to exchange authorization code: {e}",
        )

    # Store tokens in MCP server configuration
    repo = McpServerRepository(db)
    server = await repo.get_by_id_and_user(request.server_id, user_id)

    if not server:
        return McpOAuthCallbackResponse(
            success=False,
            error="MCP server not found",
        )

    # Encrypt and store tokens
    credentials = {
        "access_token": tokens.get("access_token", ""),
        "refresh_token": tokens.get("refresh_token", ""),
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_in": str(tokens.get("expires_in", "")),
        "scope": tokens.get("scope", ""),
    }

    encrypted_credentials = encryptor.encrypt(credentials)

    await repo.update_by_user(
        server.id,
        user_id,
        auth_type="oauth2",
        auth_credentials=encrypted_credentials,
    )
    await db.commit()

    return McpOAuthCallbackResponse(success=True, error=None)


@router.get(
    "/oauth/status/{server_id}",
    summary="Check OAuth authentication status",
)
async def check_oauth_status(
    server_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Check if OAuth tokens are configured for an MCP server.

    Args:
        server_id: MCP server UUID
        db: Database session
        user_id: Current user ID

    Returns:
        OAuth status information
    """
    repo = McpServerRepository(db)
    server = await repo.get_by_id_and_user(server_id, user_id)

    if not server:
        raise NotFoundError("MCP server", server_id)

    return {
        "has_oauth_tokens": server.auth_type == "oauth2" and bool(server.auth_credentials),
        "auth_type": server.auth_type,
    }


@router.post(
    "/servers/{server_id}/reauth",
    response_model=McpOAuthStartResponse,
    summary="Re-authenticate MCP server (clear credentials and start OAuth)",
)
async def reauth_mcp_server(
    server_id: UUID,
    request: McpOAuthStartRequest,
    db: DBSession,
    user_id: CurrentUserId,
) -> McpOAuthStartResponse:
    """Clear existing credentials and start a new OAuth flow.

    This endpoint allows re-authentication without deleting the server.

    Args:
        server_id: MCP server UUID
        request: OAuth start request with callback URL
        db: Database session
        user_id: Current user ID

    Returns:
        Authorization URL and state for new OAuth flow
    """
    repo = McpServerRepository(db)
    server = await repo.get_by_id_and_user(server_id, user_id)

    if not server:
        raise NotFoundError("MCP server", server_id)

    # Clear existing credentials
    await repo.update_by_user(
        server_id,
        user_id,
        auth_credentials=None,
    )
    await db.commit()

    # Use the server's URL for OAuth discovery
    server_url = request.server_url or server.server_url
    if not server_url:
        raise ValidationError("Server URL is required for OAuth re-authentication")

    return await _initiate_oauth_flow(
        server_url=server_url,
        callback_url=request.callback_url,
        user_id=user_id,
        extra_state_data={"server_id": str(server_id)},
    )
