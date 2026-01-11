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
        mock_connection.id = uuid4()
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
        mock_connection.id = uuid4()
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

        # Mock the database session for ownership verification using async generator
        async def mock_get_db():
            mock_db = AsyncMock()
            yield mock_db

        with patch("agent.api.websocket.handlers.get_db_session", mock_get_db):
            # Mock SessionRepository.verify_ownership to return True
            with patch("agent.api.websocket.handlers.SessionRepository") as MockSessionRepo:
                mock_repo = MagicMock()
                mock_repo.verify_ownership = AsyncMock(return_value=True)
                MockSessionRepo.return_value = mock_repo

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


class TestHandleMcpToolResponse:
    """Tests for _handle_mcp_tool_response method."""

    @pytest.mark.asyncio
    async def test_requires_authentication(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Requires authenticated connection."""
        mock_connection.authenticated = False

        await handler._handle_mcp_tool_response(
            mock_connection,
            {"type": "mcp_tool_call_response", "payload": {"request_id": "123"}},
        )

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "error"
        assert "Authentication required" in message.payload["error"]

    @pytest.mark.asyncio
    async def test_requires_session(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Requires subscribed session."""
        mock_connection.authenticated = True
        mock_connection.session_id = None

        await handler._handle_mcp_tool_response(
            mock_connection,
            {"type": "mcp_tool_call_response", "payload": {"request_id": "123"}},
        )

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "error"
        assert "No session subscribed" in message.payload["error"]

    @pytest.mark.asyncio
    async def test_requires_request_id(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Requires request_id in payload."""
        mock_connection.authenticated = True
        mock_connection.session_id = uuid4()

        await handler._handle_mcp_tool_response(
            mock_connection,
            {"type": "mcp_tool_call_response", "payload": {}},
        )

        # Should not send error message, just log warning
        mock_manager.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_no_executor(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Handles case when no executor found."""
        mock_connection.authenticated = True
        mock_connection.session_id = uuid4()
        mock_manager.get_mcp_executor.return_value = None

        await handler._handle_mcp_tool_response(
            mock_connection,
            {"type": "mcp_tool_call_response", "payload": {"request_id": "123"}},
        )

        mock_manager.get_mcp_executor.assert_called_once_with(mock_connection.session_id)

    @pytest.mark.asyncio
    async def test_forwards_to_executor(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Forwards response to executor."""
        mock_connection.authenticated = True
        mock_connection.session_id = uuid4()

        mock_executor = MagicMock()
        mock_manager.get_mcp_executor.return_value = mock_executor

        payload = {
            "request_id": "test-123",
            "success": True,
            "output": {"result": "data"},
            "execution_time_ms": 100,
        }

        await handler._handle_mcp_tool_response(
            mock_connection,
            {"type": "mcp_tool_call_response", "payload": payload},
        )

        mock_executor.handle_stdio_response.assert_called_once_with(
            request_id="test-123",
            success=True,
            output={"result": "data"},
            error=None,
            execution_time_ms=100,
        )


class TestHandleMcpApprovalResponse:
    """Tests for _handle_mcp_approval_response method."""

    @pytest.mark.asyncio
    async def test_requires_authentication(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Requires authenticated connection."""
        mock_connection.authenticated = False

        await handler._handle_mcp_approval_response(
            mock_connection,
            {"type": "mcp_approval_response", "payload": {"request_id": "123", "approved": True}},
        )

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "error"
        assert "Authentication required" in message.payload["error"]

    @pytest.mark.asyncio
    async def test_requires_session(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Requires subscribed session."""
        mock_connection.authenticated = True
        mock_connection.session_id = None

        await handler._handle_mcp_approval_response(
            mock_connection,
            {"type": "mcp_approval_response", "payload": {"request_id": "123", "approved": True}},
        )

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "error"
        assert "No session subscribed" in message.payload["error"]

    @pytest.mark.asyncio
    async def test_requires_request_id(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Requires request_id in payload."""
        mock_connection.authenticated = True
        mock_connection.session_id = uuid4()

        await handler._handle_mcp_approval_response(
            mock_connection,
            {"type": "mcp_approval_response", "payload": {"approved": True}},
        )

        # Should not send error message, just log warning
        mock_manager.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_forwards_approval_to_executor(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Forwards approval response to executor."""
        mock_connection.authenticated = True
        mock_connection.session_id = uuid4()

        mock_executor = MagicMock()
        mock_manager.get_mcp_executor.return_value = mock_executor

        await handler._handle_mcp_approval_response(
            mock_connection,
            {
                "type": "mcp_approval_response",
                "payload": {"request_id": "test-456", "approved": True},
            },
        )

        mock_executor.handle_approval_response.assert_called_once_with(
            request_id="test-456",
            approved=True,
        )

    @pytest.mark.asyncio
    async def test_forwards_rejection_to_executor(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Forwards rejection response to executor."""
        mock_connection.authenticated = True
        mock_connection.session_id = uuid4()

        mock_executor = MagicMock()
        mock_manager.get_mcp_executor.return_value = mock_executor

        await handler._handle_mcp_approval_response(
            mock_connection,
            {
                "type": "mcp_approval_response",
                "payload": {"request_id": "test-789", "approved": False},
            },
        )

        mock_executor.handle_approval_response.assert_called_once_with(
            request_id="test-789",
            approved=False,
        )


class TestMessageLoop:
    """Tests for _message_loop method."""

    @pytest.mark.asyncio
    async def test_processes_messages_until_disconnect(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Processes messages until WebSocketDisconnect."""
        # First call returns ping, second raises WebSocketDisconnect
        mock_connection.websocket.receive_json = AsyncMock(
            side_effect=[{"type": "ping"}, WebSocketDisconnect()]
        )

        with pytest.raises(WebSocketDisconnect):
            await handler._message_loop(mock_connection)

        # Should have processed one ping message
        assert mock_manager.send_message.call_count == 1

    @pytest.mark.asyncio
    async def test_handles_message_errors(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Handles message processing errors gracefully."""
        # First call raises error, second raises WebSocketDisconnect
        mock_connection.websocket.receive_json = AsyncMock(
            side_effect=[{"type": "unknown_type"}, WebSocketDisconnect()]
        )

        with pytest.raises(WebSocketDisconnect):
            await handler._message_loop(mock_connection)


class TestSubscribeUnauthorized:
    """Tests for subscribe authorization."""

    @pytest.mark.asyncio
    async def test_subscribe_unauthorized_user(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Denies subscription when user doesn't own session."""
        session_id = uuid4()

        async def mock_get_db():
            mock_db = AsyncMock()
            yield mock_db

        with patch("agent.api.websocket.handlers.get_db_session", mock_get_db):
            with patch("agent.api.websocket.handlers.SessionRepository") as MockSessionRepo:
                mock_repo = MagicMock()
                mock_repo.verify_ownership = AsyncMock(return_value=False)
                MockSessionRepo.return_value = mock_repo

                await handler._handle_message(
                    mock_connection,
                    {
                        "type": "subscribe",
                        "payload": {"session_id": str(session_id)},
                    },
                )

        mock_manager.subscribe_to_session.assert_not_called()
        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "error"
        assert "Not authorized" in message.payload["error"]

    @pytest.mark.asyncio
    async def test_subscribe_missing_session_id(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Denies subscription when session_id is missing."""
        await handler._handle_message(
            mock_connection,
            {
                "type": "subscribe",
                "payload": {},
            },
        )

        mock_manager.subscribe_to_session.assert_not_called()
        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        message = call_args[0][1]
        assert message.type == "error"
        assert "session_id required" in message.payload["error"]
