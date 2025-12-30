"""WebSocket handler tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect

from agent.api.websocket.handlers import WebSocketHandler
from agent.api.websocket.manager import Connection

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_manager() -> MagicMock:
    """Create mock connection manager."""
    manager = MagicMock()
    manager.connect = AsyncMock()
    manager.disconnect = AsyncMock()
    manager.subscribe_to_session = AsyncMock()
    manager.send_message = AsyncMock()
    return manager


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create mock session cache."""
    return MagicMock()


@pytest.fixture
def handler(mock_manager: MagicMock, mock_cache: MagicMock) -> WebSocketHandler:
    """Create WebSocket handler."""
    return WebSocketHandler(manager=mock_manager, cache=mock_cache)


@pytest.fixture
def mock_connection() -> Connection:
    """Create mock connection."""
    connection = MagicMock(spec=Connection)
    connection.id = "test-conn-123"
    connection.user_id = "test-user"
    connection.authenticated = True
    connection.websocket = AsyncMock()
    return connection


class TestHandleConnection:
    """Tests for handle_connection method."""

    @pytest.mark.asyncio
    async def test_authenticates_with_token(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
    ) -> None:
        """Authenticates user when token provided."""
        mock_websocket = AsyncMock()
        mock_connection = MagicMock(spec=Connection)
        mock_connection.authenticated = False
        mock_connection.websocket = mock_websocket
        mock_manager.connect.return_value = mock_connection

        # Make receive_json raise WebSocketDisconnect to end the loop
        mock_connection.websocket.receive_json = AsyncMock(side_effect=WebSocketDisconnect())

        with patch(
            "agent.api.websocket.handlers.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.return_value = "user-123"

            await handler.handle_connection(mock_websocket, token="valid-token")

            mock_auth.assert_called_once_with("valid-token")
            mock_manager.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_closes_connection_on_auth_failure(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
    ) -> None:
        """Closes connection when authentication fails."""
        mock_websocket = AsyncMock()

        with patch(
            "agent.api.websocket.handlers.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.side_effect = Exception("Invalid token")

            await handler.handle_connection(mock_websocket, token="bad-token")

            mock_websocket.close.assert_called_once_with(code=4001, reason="Authentication failed")
            mock_manager.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_subscribes_to_session(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
    ) -> None:
        """Auto-subscribes to session when provided."""
        mock_websocket = AsyncMock()
        session_id = uuid4()

        mock_connection = MagicMock(spec=Connection)
        mock_connection.authenticated = True
        mock_connection.user_id = "user-123"
        mock_connection.websocket = AsyncMock()
        mock_connection.websocket.receive_json = AsyncMock(side_effect=WebSocketDisconnect())
        mock_manager.connect.return_value = mock_connection

        with patch(
            "agent.api.websocket.handlers.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.return_value = "user-123"

            await handler.handle_connection(
                mock_websocket, session_id=session_id, token="valid-token"
            )

            mock_manager.subscribe_to_session.assert_called_once()


class TestHandleMessage:
    """Tests for _handle_message method."""

    @pytest.mark.asyncio
    async def test_handles_ping_message(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Responds to ping with pong."""
        await handler._handle_message(mock_connection, {"type": "ping"})

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "pong"

    @pytest.mark.asyncio
    async def test_handles_subscribe_message(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Subscribes to session on subscribe message."""
        session_id = uuid4()

        await handler._handle_message(
            mock_connection,
            {
                "type": "subscribe",
                "payload": {"session_id": str(session_id)},
            },
        )

        mock_manager.subscribe_to_session.assert_called_once_with(mock_connection, session_id)

    @pytest.mark.asyncio
    async def test_subscribe_requires_authentication(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Subscribe requires authenticated connection."""
        mock_connection.authenticated = False

        await handler._handle_message(
            mock_connection,
            {
                "type": "subscribe",
                "payload": {"session_id": str(uuid4())},
            },
        )

        mock_manager.subscribe_to_session.assert_not_called()
        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "error"

    @pytest.mark.asyncio
    async def test_subscribe_validates_session_id(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Subscribe validates session_id format."""
        await handler._handle_message(
            mock_connection,
            {
                "type": "subscribe",
                "payload": {"session_id": "invalid-uuid"},
            },
        )

        mock_manager.subscribe_to_session.assert_not_called()
        mock_manager.send_message.assert_called_once()


class TestHandleAuth:
    """Tests for _handle_auth method."""

    @pytest.mark.asyncio
    async def test_authenticates_with_valid_token(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Authenticates connection with valid token."""
        mock_connection.authenticated = False

        with patch(
            "agent.api.websocket.handlers.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.return_value = "user-123"

            await handler._handle_auth(
                mock_connection,
                {"type": "auth", "payload": {"token": "valid-token"}},
            )

            assert mock_connection.user_id == "user-123"
            assert mock_connection.authenticated is True
            mock_manager.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_rejects_missing_token(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Rejects auth without token."""
        mock_connection.authenticated = False

        await handler._handle_auth(
            mock_connection,
            {"type": "auth", "payload": {}},
        )

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "error"
        assert "Token required" in message.payload["error"]

    @pytest.mark.asyncio
    async def test_handles_auth_failure(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Handles authentication failure gracefully."""
        mock_connection.authenticated = False

        with patch(
            "agent.api.websocket.handlers.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.side_effect = Exception("Token expired")

            await handler._handle_auth(
                mock_connection,
                {"type": "auth", "payload": {"token": "expired-token"}},
            )

            assert mock_connection.authenticated is False
            mock_manager.send_message.assert_called_once()
            call_args = mock_manager.send_message.call_args
            message = call_args[0][1]
            assert message.type == "error"


class TestSendHelpers:
    """Tests for send helper methods."""

    @pytest.mark.asyncio
    async def test_send_auth_success(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Sends auth success message."""
        await handler._send_auth_success(mock_connection)

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "auth_success"

    @pytest.mark.asyncio
    async def test_send_error(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Sends error message."""
        await handler._send_error(mock_connection, "Test error")

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "error"
        assert message.payload["error"] == "Test error"

    @pytest.mark.asyncio
    async def test_handle_ping(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Sends pong response to ping."""
        await handler._handle_ping(mock_connection)

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "pong"
