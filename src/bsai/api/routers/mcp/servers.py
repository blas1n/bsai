"""MCP server CRUD endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from bsai.api.config import get_mcp_settings
from bsai.api.exceptions import ConflictError, NotFoundError, ValidationError
from bsai.db.repository.mcp_server_repo import McpServerRepository
from bsai.mcp.security import CredentialEncryption, McpSecurityValidator

from ...dependencies import CurrentUserId, DBSession
from ...schemas.mcp import (
    McpServerCreateRequest,
    McpServerDetailResponse,
    McpServerResponse,
    McpServerUpdateRequest,
)
from ._common import build_server_response

router = APIRouter()


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
    """Get all MCP servers for the current user."""
    repo = McpServerRepository(db)
    servers = await repo.get_by_user(user_id, is_active_only=is_active_only)
    return [await build_server_response(s, user_id) for s in servers]


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
    """Get detailed MCP server configuration."""
    repo = McpServerRepository(db)
    server = await repo.get_by_id_and_user(server_id, user_id)

    if not server:
        raise NotFoundError("MCP server", server_id)

    return await build_server_response(server, user_id, include_stdio_config)


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
    """Create a new MCP server configuration."""
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
        try:
            validator.validate_server_url(request.server_url)
        except ValueError as e:
            raise ValidationError(str(e)) from e

    elif request.transport_type == "stdio":
        if not request.command:
            raise ValidationError("command is required for stdio transport")
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
    return await build_server_response(server, user_id)


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
    """Update MCP server configuration."""
    repo = McpServerRepository(db)
    settings = get_mcp_settings()
    validator = McpSecurityValidator(settings)
    encryptor = CredentialEncryption(settings)

    update_data: dict[str, Any] = {}

    if request.name is not None:
        existing = await repo.get_by_name_and_user(request.name, user_id)
        if existing and existing.id != server_id:
            raise ConflictError("MCP server", request.name)
        update_data["name"] = request.name

    if request.description is not None:
        update_data["description"] = request.description

    if request.is_active is not None:
        update_data["is_active"] = request.is_active

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

    if request.available_tools is not None:
        update_data["available_tools"] = request.available_tools

    if request.require_approval is not None:
        update_data["require_approval"] = request.require_approval

    if request.enabled_for_worker is not None:
        update_data["enabled_for_worker"] = request.enabled_for_worker

    if request.enabled_for_qa is not None:
        update_data["enabled_for_qa"] = request.enabled_for_qa

    server = await repo.update_by_user(server_id, user_id, **update_data)

    if not server:
        raise NotFoundError("MCP server", server_id)

    await db.commit()
    return await build_server_response(server, user_id)


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
    """Soft delete MCP server configuration."""
    repo = McpServerRepository(db)
    success = await repo.delete_by_user(server_id, user_id)

    if not success:
        raise NotFoundError("MCP server", server_id)

    await db.commit()
