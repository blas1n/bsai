"""MCP OAuth endpoints."""

import base64
import hashlib
import json
import secrets
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter

from agent.api.config import get_mcp_settings
from agent.api.exceptions import NotFoundError, ValidationError
from agent.cache.redis_client import get_redis
from agent.db.repository.mcp_server_repo import McpServerRepository
from agent.mcp.security import CredentialEncryption, McpSecurityValidator

from ...dependencies import CurrentUserId, DBSession
from ...schemas.mcp import (
    McpOAuthCallbackRequest,
    McpOAuthCallbackResponse,
    McpOAuthStartRequest,
    McpOAuthStartResponse,
)

logger = structlog.get_logger()

router = APIRouter()

# OAuth state storage
OAUTH_STATE_PREFIX = "mcp_oauth_state:"
OAUTH_STATE_TTL = 600  # 10 minutes


def _build_wellknown_url(
    base_url: str, wellknown_path: str, validator: McpSecurityValidator
) -> str:
    """Build well-known URL safely with SSRF protection."""
    allowed_paths = {
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
    }
    if wellknown_path not in allowed_paths:
        raise ValueError(f"Invalid well-known path: {wellknown_path}")

    validator.validate_server_url(base_url)
    parsed = urlparse(base_url)
    normalized_url = f"{parsed.scheme}://{parsed.netloc}"

    return urljoin(normalized_url, wellknown_path)


async def _discover_oauth_metadata(server_url: str) -> dict[str, Any] | None:
    """Discover OAuth metadata from MCP server."""
    settings = get_mcp_settings()
    validator = McpSecurityValidator(settings)

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Try protected resource metadata first (RFC 9728)
        try:
            protected_resource_url = _build_wellknown_url(
                server_url, "/.well-known/oauth-protected-resource", validator
            )
            response = await client.get(protected_resource_url)
            if response.status_code == 200:
                resource_meta = response.json()
                auth_server = resource_meta.get("authorization_servers", [None])[0]
                if auth_server:
                    auth_server_meta_url = _build_wellknown_url(
                        auth_server, "/.well-known/oauth-authorization-server", validator
                    )
                    meta_response = await client.get(auth_server_meta_url)
                    if meta_response.status_code == 200:
                        result: dict[str, Any] = meta_response.json()
                        return result
        except ValueError:
            raise
        except Exception as e:
            logger.debug(
                "oauth_protected_resource_discovery_failed", server_url=server_url, error=str(e)
            )

        # Try standard OAuth metadata discovery (RFC 8414)
        try:
            oauth_server_url = _build_wellknown_url(
                server_url, "/.well-known/oauth-authorization-server", validator
            )
            response = await client.get(oauth_server_url)
            if response.status_code == 200:
                oauth_result: dict[str, Any] = response.json()
                return oauth_result
        except Exception as e:
            logger.debug(
                "oauth_authorization_server_discovery_failed", server_url=server_url, error=str(e)
            )

        # Try OpenID Connect discovery
        try:
            openid_url = _build_wellknown_url(
                server_url, "/.well-known/openid-configuration", validator
            )
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
    """Dynamically register an OAuth client (RFC 7591)."""
    settings = get_mcp_settings()
    validator = McpSecurityValidator(settings)
    validator.validate_server_url(registration_endpoint)

    registration_request = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
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
    """Common OAuth flow initiation logic."""
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

    settings = get_mcp_settings()
    validator = McpSecurityValidator(settings)
    try:
        validator.validate_server_url(auth_endpoint)
    except ValueError as e:
        raise ValidationError(f"Invalid authorization endpoint URL: {e}") from e

    # Dynamic client registration
    client_id = metadata.get("client_id")
    client_secret = None
    registration_endpoint = metadata.get("registration_endpoint")

    if not client_id and registration_endpoint:
        try:
            validator.validate_server_url(registration_endpoint)
        except ValueError as e:
            raise ValidationError(f"Invalid registration endpoint URL: {e}") from e

        client_info = await _register_oauth_client(registration_endpoint, callback_url)
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
    """Start OAuth authorization flow for an MCP server."""
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
    """Complete OAuth flow by exchanging authorization code for tokens."""
    redis_client = get_redis().client
    settings = get_mcp_settings()
    encryptor = CredentialEncryption(settings)

    # Verify state
    state_key = f"{OAUTH_STATE_PREFIX}{request.state}"
    oauth_data_str = await redis_client.get(state_key)

    if not oauth_data_str:
        return McpOAuthCallbackResponse(
            success=False,
            error="Invalid or expired OAuth state. Please try again.",
        )

    try:
        oauth_data = json.loads(oauth_data_str)
    except json.JSONDecodeError:
        return McpOAuthCallbackResponse(
            success=False,
            error="Corrupted OAuth state data.",
        )

    if oauth_data.get("user_id") != user_id:
        return McpOAuthCallbackResponse(
            success=False,
            error="OAuth state does not match current user.",
        )

    await redis_client.delete(state_key)

    # Get token endpoint
    metadata = oauth_data.get("metadata", {})
    token_endpoint = metadata.get("token_endpoint")

    if not token_endpoint:
        return McpOAuthCallbackResponse(
            success=False,
            error="OAuth metadata missing token_endpoint",
        )

    validator = McpSecurityValidator(settings)
    try:
        validator.validate_server_url(token_endpoint)
    except ValueError as e:
        return McpOAuthCallbackResponse(
            success=False,
            error=f"Invalid token endpoint URL: {e}",
        )

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

    # Store tokens
    repo = McpServerRepository(db)
    server = await repo.get_by_id_and_user(request.server_id, user_id)

    if not server:
        return McpOAuthCallbackResponse(
            success=False,
            error="MCP server not found",
        )

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
    """Check if OAuth tokens are configured for an MCP server."""
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
    """Clear existing credentials and start a new OAuth flow."""
    repo = McpServerRepository(db)
    server = await repo.get_by_id_and_user(server_id, user_id)

    if not server:
        raise NotFoundError("MCP server", server_id)

    await repo.update_by_user(server_id, user_id, auth_credentials=None)
    await db.commit()

    server_url = request.server_url or server.server_url
    if not server_url:
        raise ValidationError("Server URL is required for OAuth re-authentication")

    return await _initiate_oauth_flow(
        server_url=server_url,
        callback_url=request.callback_url,
        user_id=user_id,
        extra_state_data={"server_id": str(server_id)},
    )
