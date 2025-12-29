"""Keycloak authentication using fastapi-keycloak-middleware.

Provides authentication via middleware that validates JWTs and extracts user info.
Keycloak is only used at the API layer for JWT validation.
LangGraph nodes receive user_id after authentication, no direct Keycloak access.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import structlog
from fastapi import HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi_keycloak_middleware import KeycloakConfiguration, get_user
from jwcrypto import jwt
from jwcrypto.jwk import JWKSet

from .config import get_auth_settings

logger = structlog.get_logger()


async def user_mapper(userinfo: dict[str, Any]) -> str:
    """Extract user_id (sub claim) from token.

    Args:
        userinfo: Token claims dictionary

    Returns:
        User ID string (sub claim)
    """
    return str(userinfo.get("sub", ""))


def get_keycloak_config() -> KeycloakConfiguration:
    """Get Keycloak middleware configuration.

    Returns:
        KeycloakConfiguration for middleware setup
    """
    settings = get_auth_settings()
    return KeycloakConfiguration(
        url=settings.keycloak_url,
        realm=settings.keycloak_realm,
        client_id=settings.keycloak_client_id,
        client_secret=settings.keycloak_client_secret,
        claims=["sub"],
        reject_on_missing_claim=False,
    )


async def get_current_user_id(request: Request) -> str:
    """Get current authenticated user's ID from request.

    The middleware adds user_id to request.scope["user"].

    Args:
        request: FastAPI request object

    Returns:
        User ID string

    Raises:
        HTTPException: If user is not authenticated
    """
    user_id = await get_user(request)
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )
    return str(user_id)


async def authenticate_websocket(token: str) -> str:
    """Authenticate WebSocket with token.

    Args:
        token: JWT token string

    Returns:
        User ID from token

    Raises:
        HTTPException: If token is invalid
    """
    try:
        settings = get_auth_settings()

        async with httpx.AsyncClient() as client:
            jwks_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
            response = await client.get(jwks_url)
            jwks = JWKSet.from_json(response.text)

        decoded = jwt.JWT(key=jwks, jwt=token)
        claims = decoded.claims
        if isinstance(claims, str):
            claims = json.loads(claims)

        return str(claims.get("sub", ""))
    except Exception as e:
        logger.warning("ws_token_invalid", error=str(e))
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        ) from e


async def authenticate_websocket_connection(
    websocket: WebSocket,
    token: str | None = None,
) -> str:
    """Authenticate WebSocket connection.

    Supports two authentication methods:
    1. Query parameter: ?token=xxx
    2. First message: {"type": "auth", "token": "xxx"}

    Args:
        websocket: WebSocket connection
        token: Optional token from query parameter

    Returns:
        User ID from token

    Raises:
        WebSocketDisconnect: If authentication fails
    """
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
