"""Authentication module tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

from agent.api.auth import (
    authenticate_websocket,
    authenticate_websocket_connection,
    get_current_user_id,
    get_keycloak_config,
    user_mapper,
)
from agent.api.exceptions import AuthenticationError

if TYPE_CHECKING:
    pass


class TestUserMapper:
    """Tests for user_mapper function."""

    @pytest.mark.asyncio
    async def test_extracts_sub_claim(self) -> None:
        """user_mapper extracts sub claim from token."""
        userinfo = {"sub": "user-123", "email": "test@example.com"}
        result = await user_mapper(userinfo)
        assert result == "user-123"

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_no_sub(self) -> None:
        """user_mapper returns empty string when sub is missing."""
        userinfo = {"email": "test@example.com"}
        result = await user_mapper(userinfo)
        assert result == ""

    @pytest.mark.asyncio
    async def test_converts_sub_to_string(self) -> None:
        """user_mapper converts sub to string."""
        userinfo = {"sub": 12345}
        result = await user_mapper(userinfo)
        assert result == "12345"


class TestGetKeycloakConfig:
    """Tests for get_keycloak_config function."""

    def test_returns_keycloak_configuration(self) -> None:
        """get_keycloak_config returns KeycloakConfiguration object."""
        with patch("agent.api.auth.get_auth_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                keycloak_url="https://auth.example.com",
                keycloak_realm="test-realm",
                keycloak_client_id="test-client",
                keycloak_client_secret="secret123",
            )
            config = get_keycloak_config()

            assert config.url == "https://auth.example.com"
            assert config.realm == "test-realm"
            assert config.client_id == "test-client"


class TestGetCurrentUserId:
    """Tests for get_current_user_id function."""

    @pytest.mark.asyncio
    async def test_returns_user_id_when_authenticated(self) -> None:
        """get_current_user_id returns user ID when authenticated."""
        mock_request = MagicMock()

        with patch("agent.api.auth.get_user", new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = "user-123"
            result = await get_current_user_id(mock_request)
            assert result == "user-123"

    @pytest.mark.asyncio
    async def test_raises_401_when_not_authenticated(self) -> None:
        """get_current_user_id raises 401 when user is None."""
        mock_request = MagicMock()

        with patch("agent.api.auth.get_user", new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = None

            with pytest.raises(AuthenticationError) as exc_info:
                await get_current_user_id(mock_request)

            assert exc_info.value.status_code == 401
            assert exc_info.value.message == "Not authenticated"


class TestAuthenticateWebsocket:
    """Tests for authenticate_websocket function."""

    @pytest.mark.asyncio
    async def test_returns_user_id_on_valid_token(self) -> None:
        """authenticate_websocket returns user ID on valid token."""
        mock_response = MagicMock()
        mock_response.text = '{"keys": []}'

        mock_jwt = MagicMock()
        mock_jwt.claims = '{"sub": "user-123"}'

        with (
            patch("agent.api.auth.get_auth_settings") as mock_settings,
            patch("agent.api.auth.httpx.AsyncClient") as mock_client,
            patch("agent.api.auth.JWKSet") as mock_jwkset,
            patch("agent.api.auth.jwt.JWT", return_value=mock_jwt),
        ):
            mock_settings.return_value = MagicMock(
                keycloak_url="https://auth.example.com",
                keycloak_realm="test-realm",
            )
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            mock_jwkset.from_json.return_value = MagicMock()

            result = await authenticate_websocket("valid-token")
            assert result == "user-123"

    @pytest.mark.asyncio
    async def test_raises_401_on_invalid_token(self) -> None:
        """authenticate_websocket raises 401 on invalid token."""
        with (
            patch("agent.api.auth.get_auth_settings") as mock_settings,
            patch("agent.api.auth.httpx.AsyncClient") as mock_client,
        ):
            mock_settings.return_value = MagicMock(
                keycloak_url="https://auth.example.com",
                keycloak_realm="test-realm",
            )
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection failed")
            )

            with pytest.raises(AuthenticationError) as exc_info:
                await authenticate_websocket("invalid-token")

            assert exc_info.value.status_code == 401
            assert exc_info.value.message == "Invalid token"


class TestAuthenticateWebsocketConnection:
    """Tests for authenticate_websocket_connection function."""

    @pytest.mark.asyncio
    async def test_authenticates_with_query_token(self) -> None:
        """Authenticates using token from query parameter."""
        mock_websocket = MagicMock()

        with patch(
            "agent.api.auth.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.return_value = "user-123"
            result = await authenticate_websocket_connection(
                mock_websocket,
                token="valid-token",
            )
            assert result == "user-123"
            mock_auth.assert_called_once_with("valid-token")

    @pytest.mark.asyncio
    async def test_authenticates_with_message_token(self) -> None:
        """Authenticates using token from first message."""
        mock_websocket = AsyncMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.receive_json = AsyncMock(
            return_value={"type": "auth", "token": "message-token"}
        )

        with patch(
            "agent.api.auth.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.return_value = "user-456"
            result = await authenticate_websocket_connection(mock_websocket, token=None)
            assert result == "user-456"
            mock_auth.assert_called_once_with("message-token")

    @pytest.mark.asyncio
    async def test_raises_disconnect_on_invalid_message_type(self) -> None:
        """Raises WebSocketDisconnect on invalid message type."""
        mock_websocket = AsyncMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.receive_json = AsyncMock(return_value={"type": "not-auth", "token": "token"})
        mock_websocket.close = AsyncMock()

        with pytest.raises(WebSocketDisconnect) as exc_info:
            await authenticate_websocket_connection(mock_websocket, token=None)

        assert exc_info.value.code == 4001
        mock_websocket.close.assert_called_once_with(code=4001, reason="Expected auth message")

    @pytest.mark.asyncio
    async def test_raises_disconnect_on_missing_token(self) -> None:
        """Raises WebSocketDisconnect when token is missing from message."""
        mock_websocket = AsyncMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.receive_json = AsyncMock(return_value={"type": "auth"})
        mock_websocket.close = AsyncMock()

        with pytest.raises(WebSocketDisconnect) as exc_info:
            await authenticate_websocket_connection(mock_websocket, token=None)

        assert exc_info.value.code == 4001
        mock_websocket.close.assert_called_once_with(code=4001, reason="Token required")

    @pytest.mark.asyncio
    async def test_raises_disconnect_on_timeout(self) -> None:
        """Raises WebSocketDisconnect on authentication timeout."""
        mock_websocket = AsyncMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.receive_json = AsyncMock(side_effect=TimeoutError())
        mock_websocket.close = AsyncMock()

        with patch("agent.api.auth.asyncio.wait_for", side_effect=TimeoutError()):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                await authenticate_websocket_connection(mock_websocket, token=None)

        assert exc_info.value.code == 4001

    @pytest.mark.asyncio
    async def test_raises_disconnect_on_invalid_token(self) -> None:
        """Raises WebSocketDisconnect when token validation fails."""
        mock_websocket = AsyncMock()
        mock_websocket.close = AsyncMock()

        with patch(
            "agent.api.auth.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.side_effect = AuthenticationError(message="Invalid token")

            with pytest.raises(WebSocketDisconnect) as exc_info:
                await authenticate_websocket_connection(
                    mock_websocket,
                    token="invalid-token",
                )

            assert exc_info.value.code == 4003
