"""Keycloak authentication using fastapi-keycloak.

Provides simplified authentication leveraging fastapi-keycloak library.
Keycloak is only used at the API layer for JWT validation.
LangGraph nodes receive user_id after authentication, no direct Keycloak access.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

import structlog
from fastapi import Depends, HTTPException, Security, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi_keycloak import FastAPIKeycloak, OIDCUser

from .config import get_auth_settings

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# HTTP Bearer security scheme
security = HTTPBearer(auto_error=True)


@lru_cache(maxsize=1)
def _create_keycloak() -> FastAPIKeycloak:
    """Create Keycloak instance (cached singleton).

    Returns:
        FastAPIKeycloak instance
    """
    settings = get_auth_settings()
    return FastAPIKeycloak(
        server_url=settings.keycloak_url,
        client_id=settings.keycloak_client_id,
        client_secret=settings.keycloak_client_secret or "",
        admin_client_secret=settings.keycloak_admin_secret or "",
        realm=settings.keycloak_realm,
        callback_uri=settings.callback_uri,
    )


def get_keycloak() -> FastAPIKeycloak:
    """FastAPI dependency for Keycloak instance.

    Returns:
        FastAPIKeycloak instance
    """
    return _create_keycloak()


# Type alias for Keycloak dependency
KeycloakIDP = Annotated[FastAPIKeycloak, Depends(get_keycloak)]


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    idp: KeycloakIDP = None,  # type: ignore[assignment]
) -> OIDCUser:
    """Get current authenticated user.

    Args:
        credentials: Bearer token from Authorization header
        idp: Keycloak instance from DI

    Returns:
        OIDCUser with user info and roles

    Raises:
        HTTPException: If token is invalid
    """
    try:
        return idp.decode_token(credentials.credentials)
    except Exception as e:
        logger.warning("token_decode_failed", error=str(e))
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        ) from e


def get_current_user_id(
    user: OIDCUser = Depends(get_current_user),
) -> str:
    """Get current user's ID (sub claim).

    Args:
        user: Current user

    Returns:
        User ID string
    """
    return user.sub


def require_role(role: str):
    """Create dependency that requires a specific role.

    Args:
        role: Required role name

    Returns:
        Dependency function
    """

    def role_checker(
        user: OIDCUser = Depends(get_current_user),
    ) -> OIDCUser:
        if role not in user.roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role}' required",
            )
        return user

    return role_checker


def require_any_role(*roles: str):
    """Create dependency that requires any of the specified roles.

    Args:
        roles: Role names (any one is sufficient)

    Returns:
        Dependency function
    """

    def role_checker(
        user: OIDCUser = Depends(get_current_user),
    ) -> OIDCUser:
        if not any(role in user.roles for role in roles):
            raise HTTPException(
                status_code=403,
                detail=f"One of roles {roles} required",
            )
        return user

    return role_checker


async def authenticate_websocket(token: str) -> OIDCUser:
    """Authenticate WebSocket with token.

    Args:
        token: JWT token string

    Returns:
        OIDCUser from token

    Raises:
        HTTPException: If token is invalid
    """
    idp = get_keycloak()
    try:
        return idp.decode_token(token)
    except Exception as e:
        logger.warning("ws_token_invalid", error=str(e))
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        ) from e


async def authenticate_websocket_connection(
    websocket: WebSocket,
    token: str | None = None,
) -> OIDCUser:
    """Authenticate WebSocket connection.

    Supports two authentication methods:
    1. Query parameter: ?token=xxx
    2. First message: {"type": "auth", "token": "xxx"}

    Args:
        websocket: WebSocket connection
        token: Optional token from query parameter

    Returns:
        OIDCUser from token

    Raises:
        WebSocketDisconnect: If authentication fails
    """
    from fastapi import WebSocketDisconnect

    if token is None:
        await websocket.accept()
        try:
            auth_msg = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=10.0,
            )
            if auth_msg.get("type") != "auth":
                await websocket.close(code=4001, reason="Expected auth message")
                raise WebSocketDisconnect(code=4001)
            token = auth_msg.get("token")
            if not token:
                await websocket.close(code=4001, reason="Token required")
                raise WebSocketDisconnect(code=4001)
        except TimeoutError:
            await websocket.close(code=4001, reason="Authentication timeout")
            raise WebSocketDisconnect(code=4001) from None

    try:
        return await authenticate_websocket(token)
    except HTTPException as e:
        await websocket.close(code=4003, reason=str(e.detail))
        raise WebSocketDisconnect(code=4003) from e
