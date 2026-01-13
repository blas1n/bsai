"""Tests for WebSocket message handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect

from agent.api.schemas import WSMessageType
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
    manager.get_mcp_executor = MagicMock(return_value=None)
    manager.set_breakpoint_enabled = MagicMock()
    return manager


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create mock session cache."""
    return MagicMock()


@pytest.fixture
def handler(mock_manager: MagicMock, mock_cache: MagicMock) -> WebSocketHandler:
    """Create WebSocket handler."""
    return WebSocketHandler(mock_manager, mock_cache)


@pytest.fixture
def mock_connection() -> Connection:
    """Create mock connection."""
    ws = MagicMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()

    connection = Connection(
        id=str(uuid4()),
        websocket=ws,
        authenticated=True,
        user_id="test-user",
        session_id=uuid4(),
    )
    return connection


class TestHandleConnection:
    """Tests for handle_connection method."""

    @pytest.mark.asyncio
    async def test_accepts_connection_without_auth(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
    ) -> None:
        """Accepts connection without authentication token."""
        mock_ws = MagicMock()
        mock_ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect())
        mock_ws.close = AsyncMock()

        mock_conn = Connection(id=str(uuid4()), websocket=mock_ws)
        mock_manager.connect.return_value = mock_conn

        await handler.handle_connection(mock_ws)

        mock_manager.connect.assert_called_once()
        mock_manager.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticates_with_token(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
    ) -> None:
        """Authenticates connection with token."""
        mock_ws = MagicMock()
        mock_ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect())
        mock_ws.close = AsyncMock()

        mock_conn = Connection(id=str(uuid4()), websocket=mock_ws)
        mock_conn.authenticated = False
        mock_manager.connect.return_value = mock_conn

        with patch(
            "agent.api.websocket.handlers.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.return_value = "test-user"

            await handler.handle_connection(mock_ws, token="valid-token")

            mock_auth.assert_called_once_with("valid-token")
            mock_manager.connect.assert_called_once_with(mock_ws, "test-user")

    @pytest.mark.asyncio
    async def test_closes_on_auth_failure(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
    ) -> None:
        """Closes connection on authentication failure."""
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock()

        with patch(
            "agent.api.websocket.handlers.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.side_effect = Exception("Invalid token")

            await handler.handle_connection(mock_ws, token="invalid-token")

            mock_ws.close.assert_called_once_with(code=4001, reason="Authentication failed")
            mock_manager.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_subscribes_to_session(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
    ) -> None:
        """Auto-subscribes to session when provided."""
        mock_ws = MagicMock()
        mock_ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect())
        mock_ws.close = AsyncMock()

        session_id = uuid4()
        mock_conn = Connection(id=str(uuid4()), websocket=mock_ws, authenticated=True)
        mock_manager.connect.return_value = mock_conn

        await handler.handle_connection(mock_ws, session_id=session_id)

        mock_manager.subscribe_to_session.assert_called_once_with(mock_conn, session_id)

    @pytest.mark.asyncio
    async def test_handles_general_exception(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
    ) -> None:
        """Handles general exceptions gracefully."""
        mock_ws = MagicMock()
        mock_ws.receive_json = AsyncMock(side_effect=Exception("Unexpected error"))
        mock_ws.close = AsyncMock()

        mock_conn = Connection(id=str(uuid4()), websocket=mock_ws)
        mock_manager.connect.return_value = mock_conn

        await handler.handle_connection(mock_ws)

        mock_manager.disconnect.assert_called_once()


class TestHandleAuth:
    """Tests for _handle_auth method."""

    @pytest.mark.asyncio
    async def test_authenticates_successfully(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Successfully authenticates connection."""
        mock_connection.authenticated = False

        with patch(
            "agent.api.websocket.handlers.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.return_value = "new-user-id"

            await handler._handle_auth(
                mock_connection,
                {"type": "auth", "payload": {"token": "valid-token"}},
            )

            assert mock_connection.authenticated is True
            assert mock_connection.user_id == "new-user-id"
            mock_manager.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_fails_without_token(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails when token not provided."""
        await handler._handle_auth(
            mock_connection,
            {"type": "auth", "payload": {}},
        )

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        assert call_args[0][1].type == WSMessageType.ERROR

    @pytest.mark.asyncio
    async def test_fails_on_invalid_token(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails on invalid token."""
        mock_connection.authenticated = False

        with patch(
            "agent.api.websocket.handlers.authenticate_websocket",
            new_callable=AsyncMock,
        ) as mock_auth:
            mock_auth.side_effect = Exception("Invalid token")

            await handler._handle_auth(
                mock_connection,
                {"type": "auth", "payload": {"token": "bad-token"}},
            )

            assert mock_connection.authenticated is False
            mock_manager.send_message.assert_called()


class TestHandleSubscribe:
    """Tests for _handle_subscribe method."""

    @pytest.mark.asyncio
    async def test_subscribes_successfully(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Successfully subscribes to session."""
        session_id = uuid4()

        with patch("agent.api.websocket.handlers.get_db_session") as mock_get_db:

            async def mock_generator():
                mock_db = MagicMock()
                yield mock_db

            mock_get_db.return_value = mock_generator()

            with patch("agent.api.websocket.handlers.SessionRepository") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.verify_ownership = AsyncMock(return_value=True)
                mock_repo_class.return_value = mock_repo

                await handler._handle_subscribe(
                    mock_connection,
                    {"type": "subscribe", "payload": {"session_id": str(session_id)}},
                )

                mock_manager.subscribe_to_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_fails_without_authentication(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails when not authenticated."""
        mock_connection.authenticated = False

        await handler._handle_subscribe(
            mock_connection,
            {"type": "subscribe", "payload": {"session_id": str(uuid4())}},
        )

        mock_manager.subscribe_to_session.assert_not_called()
        mock_manager.send_message.assert_called_once()
        assert mock_manager.send_message.call_args[0][1].type == WSMessageType.ERROR

    @pytest.mark.asyncio
    async def test_fails_without_session_id(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails when session_id not provided."""
        await handler._handle_subscribe(
            mock_connection,
            {"type": "subscribe", "payload": {}},
        )

        mock_manager.subscribe_to_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_with_invalid_uuid(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails with invalid session_id UUID."""
        await handler._handle_subscribe(
            mock_connection,
            {"type": "subscribe", "payload": {"session_id": "not-a-uuid"}},
        )

        mock_manager.subscribe_to_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_when_not_owner(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails when user doesn't own session."""
        session_id = uuid4()

        with patch("agent.api.websocket.handlers.get_db_session") as mock_get_db:

            async def mock_generator():
                mock_db = MagicMock()
                yield mock_db

            mock_get_db.return_value = mock_generator()

            with patch("agent.api.websocket.handlers.SessionRepository") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.verify_ownership = AsyncMock(return_value=False)
                mock_repo_class.return_value = mock_repo

                await handler._handle_subscribe(
                    mock_connection,
                    {"type": "subscribe", "payload": {"session_id": str(session_id)}},
                )

                mock_manager.subscribe_to_session.assert_not_called()


class TestHandlePing:
    """Tests for _handle_ping method."""

    @pytest.mark.asyncio
    async def test_sends_pong(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Sends pong response."""
        await handler._handle_ping(mock_connection)

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        assert call_args[0][1].type == WSMessageType.PONG


class TestHandleMcpToolResponse:
    """Tests for _handle_mcp_tool_response method."""

    @pytest.mark.asyncio
    async def test_forwards_to_executor(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Forwards tool response to executor."""
        mock_executor = MagicMock()
        mock_executor.handle_stdio_response = MagicMock()
        mock_manager.get_mcp_executor.return_value = mock_executor

        await handler._handle_mcp_tool_response(
            mock_connection,
            {
                "type": "mcp_tool_call_response",
                "payload": {
                    "request_id": "req-123",
                    "success": True,
                    "output": "Result",
                },
            },
        )

        mock_executor.handle_stdio_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_fails_without_authentication(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails when not authenticated."""
        mock_connection.authenticated = False

        await handler._handle_mcp_tool_response(
            mock_connection,
            {"type": "mcp_tool_call_response", "payload": {"request_id": "123"}},
        )

        mock_manager.get_mcp_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_without_session(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails when no session subscribed."""
        mock_connection.session_id = None

        await handler._handle_mcp_tool_response(
            mock_connection,
            {"type": "mcp_tool_call_response", "payload": {"request_id": "123"}},
        )

        mock_manager.get_mcp_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_missing_executor(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Handles missing executor gracefully."""
        mock_manager.get_mcp_executor.return_value = None

        # Should not raise
        await handler._handle_mcp_tool_response(
            mock_connection,
            {
                "type": "mcp_tool_call_response",
                "payload": {"request_id": "123"},
            },
        )


class TestHandleMcpApprovalResponse:
    """Tests for _handle_mcp_approval_response method."""

    @pytest.mark.asyncio
    async def test_forwards_to_executor(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Forwards approval response to executor."""
        mock_executor = MagicMock()
        mock_executor.handle_approval_response = MagicMock()
        mock_manager.get_mcp_executor.return_value = mock_executor

        await handler._handle_mcp_approval_response(
            mock_connection,
            {
                "type": "mcp_approval_response",
                "payload": {
                    "request_id": "req-456",
                    "approved": True,
                },
            },
        )

        mock_executor.handle_approval_response.assert_called_once_with(
            request_id="req-456",
            approved=True,
        )

    @pytest.mark.asyncio
    async def test_fails_without_authentication(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails when not authenticated."""
        mock_connection.authenticated = False

        await handler._handle_mcp_approval_response(
            mock_connection,
            {"type": "mcp_approval_response", "payload": {"request_id": "123"}},
        )

        mock_manager.get_mcp_executor.assert_not_called()


class TestHandleBreakpointConfig:
    """Tests for _handle_breakpoint_config method."""

    @pytest.mark.asyncio
    async def test_updates_breakpoint_config(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Updates breakpoint configuration."""
        task_id = uuid4()

        await handler._handle_breakpoint_config(
            mock_connection,
            {
                "type": "breakpoint_config",
                "payload": {
                    "task_id": str(task_id),
                    "breakpoint_enabled": True,
                },
            },
        )

        mock_manager.set_breakpoint_enabled.assert_called_once_with(task_id, True)

    @pytest.mark.asyncio
    async def test_fails_without_authentication(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails when not authenticated."""
        mock_connection.authenticated = False

        await handler._handle_breakpoint_config(
            mock_connection,
            {"type": "breakpoint_config", "payload": {"task_id": str(uuid4())}},
        )

        mock_manager.set_breakpoint_enabled.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_with_invalid_task_id(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails with invalid task_id UUID."""
        await handler._handle_breakpoint_config(
            mock_connection,
            {
                "type": "breakpoint_config",
                "payload": {"task_id": "not-a-uuid"},
            },
        )

        mock_manager.set_breakpoint_enabled.assert_not_called()


class TestHandleMessage:
    """Tests for _handle_message routing."""

    @pytest.mark.asyncio
    async def test_routes_auth_message(
        self,
        handler: WebSocketHandler,
        mock_connection: Connection,
    ) -> None:
        """Routes auth message to handler."""
        with patch.object(handler, "_handle_auth", new_callable=AsyncMock) as mock_auth:
            await handler._handle_message(
                mock_connection,
                {"type": WSMessageType.AUTH},
            )

            mock_auth.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_subscribe_message(
        self,
        handler: WebSocketHandler,
        mock_connection: Connection,
    ) -> None:
        """Routes subscribe message to handler."""
        with patch.object(handler, "_handle_subscribe", new_callable=AsyncMock) as mock_sub:
            await handler._handle_message(
                mock_connection,
                {"type": WSMessageType.SUBSCRIBE},
            )

            mock_sub.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_ping_message(
        self,
        handler: WebSocketHandler,
        mock_connection: Connection,
    ) -> None:
        """Routes ping message to handler."""
        with patch.object(handler, "_handle_ping", new_callable=AsyncMock) as mock_ping:
            await handler._handle_message(
                mock_connection,
                {"type": WSMessageType.PING},
            )

            mock_ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_unknown_message_type(
        self,
        handler: WebSocketHandler,
        mock_connection: Connection,
    ) -> None:
        """Handles unknown message type gracefully."""
        # Should not raise
        await handler._handle_message(
            mock_connection,
            {"type": "unknown_type"},
        )
