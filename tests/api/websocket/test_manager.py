"""WebSocket connection manager tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.api.websocket.manager import Connection, ConnectionManager

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create mock session cache."""
    cache = MagicMock()
    cache.increment_ws_connection_count = AsyncMock()
    cache.decrement_ws_connection_count = AsyncMock()
    cache.register_ws_connection = AsyncMock()
    cache.unregister_ws_connection = AsyncMock()
    return cache


@pytest.fixture
def manager(mock_cache: MagicMock) -> ConnectionManager:
    """Create connection manager."""
    return ConnectionManager(cache=mock_cache)


@pytest.fixture
def mock_websocket() -> AsyncMock:
    """Create mock WebSocket."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestConnect:
    """Tests for connect method."""

    @pytest.mark.asyncio
    async def test_accepts_websocket(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Accepts WebSocket connection."""
        await manager.connect(mock_websocket)

        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_connection_with_user(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Creates connection with authenticated user."""
        connection = await manager.connect(mock_websocket, user_id="user-123")

        assert connection.user_id == "user-123"
        assert connection.authenticated is True

    @pytest.mark.asyncio
    async def test_creates_connection_without_user(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Creates connection without authentication."""
        connection = await manager.connect(mock_websocket)

        assert connection.user_id is None
        assert connection.authenticated is False

    @pytest.mark.asyncio
    async def test_stores_connection(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Stores connection in manager."""
        connection = await manager.connect(mock_websocket)

        assert connection.id in manager._connections


class TestDisconnect:
    """Tests for disconnect method."""

    @pytest.mark.asyncio
    async def test_removes_connection(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Removes connection from manager."""
        connection = await manager.connect(mock_websocket)

        await manager.disconnect(connection)

        assert connection.id not in manager._connections

    @pytest.mark.asyncio
    async def test_removes_from_session_subscription(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Removes connection from session subscription."""
        connection = await manager.connect(mock_websocket, user_id="user-123")
        session_id = uuid4()
        await manager.subscribe_to_session(connection, session_id)

        await manager.disconnect(connection)

        assert connection.id not in manager._session_connections.get(session_id, set())


class TestSubscribeToSession:
    """Tests for subscribe_to_session method."""

    @pytest.mark.asyncio
    async def test_subscribes_to_session(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Subscribes connection to session."""
        connection = await manager.connect(mock_websocket, user_id="user-123")
        session_id = uuid4()

        await manager.subscribe_to_session(connection, session_id)

        assert connection.session_id == session_id
        assert connection.id in manager._session_connections[session_id]

    @pytest.mark.asyncio
    async def test_unsubscribes_from_previous_session(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Unsubscribes from previous session when subscribing to new one."""
        connection = await manager.connect(mock_websocket, user_id="user-123")
        old_session = uuid4()
        new_session = uuid4()

        await manager.subscribe_to_session(connection, old_session)
        await manager.subscribe_to_session(connection, new_session)

        assert connection.session_id == new_session
        assert connection.id not in manager._session_connections.get(old_session, set())


class TestSendMessage:
    """Tests for send_message method."""

    @pytest.mark.asyncio
    async def test_sends_message_to_connection(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Sends message to single connection."""
        connection = await manager.connect(mock_websocket)

        message = MagicMock()
        message.model_dump.return_value = {"type": "test", "payload": {}}

        await manager.send_message(connection, message)

        mock_websocket.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_send_error(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Handles error when sending message."""
        connection = await manager.connect(mock_websocket)
        mock_websocket.send_json.side_effect = Exception("Send failed")

        message = MagicMock()
        message.model_dump.return_value = {"type": "test"}

        # Should not raise
        await manager.send_message(connection, message)


class TestBroadcastToSession:
    """Tests for broadcast_to_session method."""

    @pytest.mark.asyncio
    async def test_broadcasts_to_all_session_connections(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Broadcasts message to all connections subscribed to session."""
        session_id = uuid4()

        # Create multiple connections
        ws1, ws2 = AsyncMock(), AsyncMock()
        ws1.accept, ws2.accept = AsyncMock(), AsyncMock()
        ws1.send_json, ws2.send_json = AsyncMock(), AsyncMock()

        conn1 = await manager.connect(ws1, user_id="user-1")
        conn2 = await manager.connect(ws2, user_id="user-2")

        await manager.subscribe_to_session(conn1, session_id)
        await manager.subscribe_to_session(conn2, session_id)

        message = MagicMock()
        message.model_dump.return_value = {"type": "test"}

        await manager.broadcast_to_session(session_id, message)

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_session_with_no_connections(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Does nothing when session has no connections."""
        session_id = uuid4()
        message = MagicMock()
        message.model_dump.return_value = {"type": "test"}

        # Should not raise
        await manager.broadcast_to_session(session_id, message)


class TestGetSessionConnectionCount:
    """Tests for get_session_connection_count method."""

    @pytest.mark.asyncio
    async def test_returns_session_connection_count(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Returns count of connections for a session."""
        connection = await manager.connect(mock_websocket, user_id="user-123")
        session_id = uuid4()
        await manager.subscribe_to_session(connection, session_id)

        count = manager.get_session_connection_count(session_id)

        assert count == 1

    def test_returns_zero_for_unknown_session(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Returns 0 for session with no connections."""
        session_id = uuid4()

        count = manager.get_session_connection_count(session_id)

        assert count == 0


class TestGetTotalConnections:
    """Tests for get_total_connections method."""

    @pytest.mark.asyncio
    async def test_returns_total_connection_count(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Returns total number of connections."""
        ws1, ws2 = AsyncMock(), AsyncMock()
        ws1.accept, ws2.accept = AsyncMock(), AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)

        count = manager.get_total_connections()

        assert count == 2

    def test_returns_zero_when_no_connections(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Returns 0 when no connections."""
        count = manager.get_total_connections()

        assert count == 0


class TestConnection:
    """Tests for Connection dataclass."""

    def test_creates_connection(self) -> None:
        """Creates connection with required fields."""
        ws = MagicMock()
        conn = Connection(id="conn-123", websocket=ws)

        assert conn.id == "conn-123"
        assert conn.websocket is ws
        assert conn.session_id is None
        assert conn.user_id is None
        assert conn.authenticated is False

    def test_creates_authenticated_connection(self) -> None:
        """Creates authenticated connection."""
        ws = MagicMock()
        conn = Connection(
            id="conn-123",
            websocket=ws,
            user_id="user-123",
            authenticated=True,
        )

        assert conn.user_id == "user-123"
        assert conn.authenticated is True


class TestUnsubscribeFromSession:
    """Tests for unsubscribe_from_session method."""

    @pytest.mark.asyncio
    async def test_unsubscribes_from_session(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Unsubscribes connection from session."""
        connection = await manager.connect(mock_websocket, user_id="user-123")
        session_id = uuid4()
        await manager.subscribe_to_session(connection, session_id)

        await manager.unsubscribe_from_session(connection)

        assert connection.session_id is None
        assert connection.id not in manager._session_connections.get(session_id, set())

    @pytest.mark.asyncio
    async def test_no_op_when_not_subscribed(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Does nothing when connection is not subscribed to any session."""
        connection = await manager.connect(mock_websocket)

        # Should not raise
        await manager.unsubscribe_from_session(connection)

        assert connection.session_id is None


class TestBroadcastToUser:
    """Tests for broadcast_to_user method."""

    @pytest.mark.asyncio
    async def test_broadcasts_to_all_user_connections(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Broadcasts message to all connections for a user."""
        ws1, ws2 = AsyncMock(), AsyncMock()
        ws1.accept, ws2.accept = AsyncMock(), AsyncMock()
        ws1.send_json, ws2.send_json = AsyncMock(), AsyncMock()

        await manager.connect(ws1, user_id="user-123")
        await manager.connect(ws2, user_id="user-123")

        message = MagicMock()
        message.model_dump.return_value = {"type": "test"}

        count = await manager.broadcast_to_user("user-123", message)

        assert count == 2
        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_zero_for_unknown_user(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Returns 0 when user has no connections."""
        message = MagicMock()
        message.model_dump.return_value = {"type": "test"}

        count = await manager.broadcast_to_user("unknown-user", message)

        assert count == 0

    @pytest.mark.asyncio
    async def test_does_not_send_to_other_users(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Does not send to other users' connections."""
        ws1, ws2 = AsyncMock(), AsyncMock()
        ws1.accept, ws2.accept = AsyncMock(), AsyncMock()
        ws1.send_json, ws2.send_json = AsyncMock(), AsyncMock()

        await manager.connect(ws1, user_id="user-123")
        await manager.connect(ws2, user_id="user-456")

        message = MagicMock()
        message.model_dump.return_value = {"type": "test"}

        count = await manager.broadcast_to_user("user-123", message)

        assert count == 1
        ws1.send_json.assert_called_once()
        ws2.send_json.assert_not_called()


class TestMcpExecutor:
    """Tests for MCP executor methods."""

    @pytest.mark.asyncio
    async def test_register_mcp_executor(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Registers MCP executor for a session."""
        session_id = uuid4()
        mock_executor = MagicMock()

        manager.register_mcp_executor(session_id, mock_executor)

        assert manager._mcp_executors[session_id] == mock_executor

    @pytest.mark.asyncio
    async def test_get_mcp_executor(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Gets MCP executor for a session."""
        session_id = uuid4()
        mock_executor = MagicMock()
        manager.register_mcp_executor(session_id, mock_executor)

        result = manager.get_mcp_executor(session_id)

        assert result == mock_executor

    @pytest.mark.asyncio
    async def test_get_mcp_executor_returns_none_for_unknown_session(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Returns None when session has no executor."""
        session_id = uuid4()

        result = manager.get_mcp_executor(session_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_unregister_mcp_executor(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Unregisters MCP executor for a session."""
        session_id = uuid4()
        mock_executor = MagicMock()
        manager.register_mcp_executor(session_id, mock_executor)

        manager.unregister_mcp_executor(session_id)

        assert session_id not in manager._mcp_executors

    @pytest.mark.asyncio
    async def test_unregister_mcp_executor_no_op_for_unknown_session(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Does nothing when session has no executor."""
        session_id = uuid4()

        # Should not raise
        manager.unregister_mcp_executor(session_id)

        assert session_id not in manager._mcp_executors


class TestSendMessageEdgeCases:
    """Tests for send_message edge cases."""

    @pytest.mark.asyncio
    async def test_handles_websocket_disconnect(
        self,
        manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Handles WebSocketDisconnect when sending."""
        from fastapi import WebSocketDisconnect

        connection = await manager.connect(mock_websocket)
        mock_websocket.send_json.side_effect = WebSocketDisconnect()

        message = MagicMock()
        message.model_dump.return_value = {"type": "test"}

        result = await manager.send_message(connection, message)

        assert result is False
        assert connection.id not in manager._connections


class TestBroadcastToSessionEdgeCases:
    """Tests for broadcast_to_session edge cases."""

    @pytest.mark.asyncio
    async def test_handles_failed_connections(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Handles failed connections during broadcast."""
        from fastapi import WebSocketDisconnect

        session_id = uuid4()

        ws1, ws2 = AsyncMock(), AsyncMock()
        ws1.accept, ws2.accept = AsyncMock(), AsyncMock()
        ws1.send_json = AsyncMock()
        ws2.send_json = AsyncMock(side_effect=WebSocketDisconnect())

        conn1 = await manager.connect(ws1, user_id="user-1")
        conn2 = await manager.connect(ws2, user_id="user-2")

        await manager.subscribe_to_session(conn1, session_id)
        await manager.subscribe_to_session(conn2, session_id)

        message = MagicMock()
        message.type = "test"
        message.model_dump.return_value = {"type": "test"}

        count = await manager.broadcast_to_session(session_id, message)

        assert count == 1
        # conn2 should be disconnected
        assert conn2.id not in manager._connections

    @pytest.mark.asyncio
    async def test_handles_exception_during_broadcast(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Handles exceptions during broadcast."""
        session_id = uuid4()

        ws1, ws2 = AsyncMock(), AsyncMock()
        ws1.accept, ws2.accept = AsyncMock(), AsyncMock()
        ws1.send_json = AsyncMock()
        ws2.send_json = AsyncMock(side_effect=Exception("Network error"))

        conn1 = await manager.connect(ws1, user_id="user-1")
        conn2 = await manager.connect(ws2, user_id="user-2")

        await manager.subscribe_to_session(conn1, session_id)
        await manager.subscribe_to_session(conn2, session_id)

        message = MagicMock()
        message.type = "test"
        message.model_dump.return_value = {"type": "test"}

        count = await manager.broadcast_to_session(session_id, message)

        assert count == 1
