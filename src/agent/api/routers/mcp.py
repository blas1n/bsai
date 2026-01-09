"""MCP (Model Context Protocol) server management endpoints."""

import time
from uuid import UUID

from fastapi import APIRouter, status
from mcp import ClientSession
from mcp.client.sse import sse_client

from agent.api.config import get_mcp_settings
from agent.api.exceptions import ConflictError, NotFoundError, ValidationError
from agent.db.repository.mcp_server_repo import McpServerRepository
from agent.db.repository.mcp_tool_log_repo import McpToolLogRepository
from agent.mcp.security import CredentialEncryption, McpSecurityValidator

from ..dependencies import CurrentUserId, DBSession
from ..schemas.mcp import (
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

router = APIRouter(prefix="/mcp", tags=["mcp"])


async def _build_server_response(
    server, user_id: str, include_stdio_config: bool = False
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
    update_data = {}

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
    encryptor = CredentialEncryption(settings)
    headers: dict[str, str] | None = None

    if server.auth_credentials:
        try:
            credentials = encryptor.decrypt(server.auth_credentials)
            if server.auth_type == "bearer":
                headers = {"Authorization": f"Bearer {credentials.get('token', '')}"}
            elif server.auth_type == "api_key":
                headers = {
                    credentials.get("header_name", "X-API-Key"): credentials.get("api_key", "")
                }
        except Exception:
            pass  # Continue without auth if decryption fails

    try:
        # Measure latency and load tools via MCP SDK
        start_time = time.monotonic()

        async with sse_client(url=server.server_url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
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
            error=str(e),
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
        settings = get_mcp_settings()
        encryptor = CredentialEncryption(settings)
        headers: dict[str, str] | None = None

        if server.auth_credentials:
            try:
                credentials = encryptor.decrypt(server.auth_credentials)
                if server.auth_type == "bearer":
                    headers = {"Authorization": f"Bearer {credentials.get('token', '')}"}
                elif server.auth_type == "api_key":
                    headers = {
                        credentials.get("header_name", "X-API-Key"): credentials.get("api_key", "")
                    }
            except Exception:
                pass

        # Load tools from MCP server via MCP SDK
        async with sse_client(url=server.server_url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()

        result = []
        for tool in tools_result.tools:
            result.append(
                McpToolSchema(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema if tool.inputSchema else {},
                )
            )

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
