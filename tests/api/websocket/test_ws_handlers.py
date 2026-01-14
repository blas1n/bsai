"""Tests for WebSocket message handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.api.schemas import WSMessageType
from agent.api.websocket.handlers import WebSocketHandler
from agent.api.websocket.manager import Connection
from agent.services import BreakpointService

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
def mock_breakpoint_service() -> MagicMock:
    """Create mock breakpoint service."""
    service = MagicMock(spec=BreakpointService)
    service.set_breakpoint_enabled = MagicMock()
    return service


@pytest.fixture
def handler(
    mock_manager: MagicMock,
    mock_cache: MagicMock,
    mock_breakpoint_service: MagicMock,
) -> WebSocketHandler:
    """Create WebSocket handler."""
    return WebSocketHandler(mock_manager, mock_cache, mock_breakpoint_service)


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
        """Fails when session_id is invalid UUID."""
        await handler._handle_subscribe(
            mock_connection,
            {"type": "subscribe", "payload": {"session_id": "not-a-uuid"}},
        )

        mock_manager.subscribe_to_session.assert_not_called()
        mock_manager.send_message.assert_called()


class TestHandleMessage:
    """Tests for _handle_message method."""

    @pytest.mark.asyncio
    async def test_routes_auth_message(
        self,
        handler: WebSocketHandler,
        mock_connection: Connection,
    ) -> None:
        """Routes auth message to _handle_auth."""
        with patch.object(handler, "_handle_auth", new_callable=AsyncMock) as mock_auth:
            await handler._handle_message(
                mock_connection,
                {"type": "auth", "payload": {"token": "test"}},
            )

            mock_auth.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_subscribe_message(
        self,
        handler: WebSocketHandler,
        mock_connection: Connection,
    ) -> None:
        """Routes subscribe message to _handle_subscribe."""
        with patch.object(handler, "_handle_subscribe", new_callable=AsyncMock) as mock_sub:
            await handler._handle_message(
                mock_connection,
                {"type": "subscribe", "payload": {"session_id": str(uuid4())}},
            )

            mock_sub.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_ping_message(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Routes ping message and responds with pong."""
        await handler._handle_message(
            mock_connection,
            {"type": "ping", "payload": {}},
        )

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        assert call_args[0][1].type == WSMessageType.PONG

    @pytest.mark.asyncio
    async def test_handles_unknown_message_type(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Handles unknown message type gracefully (just logs, no error sent)."""
        await handler._handle_message(
            mock_connection,
            {"type": "unknown_type", "payload": {}},
        )

        # Unknown types are just logged, no error message sent
        mock_manager.send_message.assert_not_called()


class TestHandleBreakpointConfig:
    """Tests for _handle_breakpoint_config method."""

    @pytest.mark.asyncio
    async def test_enables_breakpoint(
        self,
        handler: WebSocketHandler,
        mock_breakpoint_service: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Enables breakpoint for task."""
        task_id = uuid4()

        await handler._handle_breakpoint_config(
            mock_connection,
            {
                "type": "breakpoint_config",
                "payload": {"task_id": str(task_id), "breakpoint_enabled": True},
            },
        )

        mock_breakpoint_service.set_breakpoint_enabled.assert_called_once_with(task_id, True)

    @pytest.mark.asyncio
    async def test_disables_breakpoint(
        self,
        handler: WebSocketHandler,
        mock_breakpoint_service: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Disables breakpoint for task."""
        task_id = uuid4()

        await handler._handle_breakpoint_config(
            mock_connection,
            {
                "type": "breakpoint_config",
                "payload": {"task_id": str(task_id), "breakpoint_enabled": False},
            },
        )

        mock_breakpoint_service.set_breakpoint_enabled.assert_called_once_with(task_id, False)

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
            {
                "type": "breakpoint_config",
                "payload": {"task_id": str(uuid4()), "breakpoint_enabled": True},
            },
        )

        mock_manager.set_breakpoint_enabled.assert_not_called()
        mock_manager.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_fails_without_task_id(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails when task_id not provided."""
        await handler._handle_breakpoint_config(
            mock_connection,
            {"type": "breakpoint_config", "payload": {"breakpoint_enabled": True}},
        )

        mock_manager.set_breakpoint_enabled.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_with_invalid_task_id(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Fails when task_id is invalid UUID."""
        await handler._handle_breakpoint_config(
            mock_connection,
            {
                "type": "breakpoint_config",
                "payload": {"task_id": "not-a-uuid", "breakpoint_enabled": True},
            },
        )

        mock_manager.set_breakpoint_enabled.assert_not_called()
        mock_manager.send_message.assert_called()


class TestSendError:
    """Tests for _send_error method."""

    @pytest.mark.asyncio
    async def test_sends_error_message(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Sends error message to connection."""
        await handler._send_error(mock_connection, "Test error")

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        assert call_args[0][1].type == WSMessageType.ERROR
        assert "Test error" in str(call_args[0][1].payload)


class TestSendAuthSuccess:
    """Tests for _send_auth_success method."""

    @pytest.mark.asyncio
    async def test_sends_auth_success(
        self,
        handler: WebSocketHandler,
        mock_manager: MagicMock,
        mock_connection: Connection,
    ) -> None:
        """Sends auth success message."""
        await handler._send_auth_success(mock_connection)

        mock_manager.send_message.assert_called_once()
        call_args = mock_manager.send_message.call_args
        assert call_args[0][1].type == WSMessageType.AUTH_SUCCESS
