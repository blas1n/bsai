"""WebSocket connection manager tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

from agent.api.schemas import WSMessage, WSMessageType
from agent.api.websocket import ConnectionManager

if TYPE_CHECKING:
    pass


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self) -> None:
        self.accepted = False
        self.closed = False
        self.close_code: int | None = None
        self.messages_sent: list[dict[str, Any]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.close_code = code

    async def send_json(self, data: dict[str, Any]) -> None:
        self.messages_sent.append(data)


class MockSessionCache:
    """Mock session cache for testing."""

    def __init__(self) -> None:
        self._connections: dict[str, set[str]] = {}

    async def register_ws_connection(
        self,
        session_id: Any,
        connection_id: str,
    ) -> None:
        key = str(session_id)
        if key not in self._connections:
            self._connections[key] = set()
        self._connections[key].add(connection_id)

    async def unregister_ws_connection(
        self,
        session_id: Any,
        connection_id: str,
    ) -> None:
        key = str(session_id)
        if key in self._connections:
            self._connections[key].discard(connection_id)


@pytest.fixture
def mock_ws_cache() -> MockSessionCache:
    """Create mock session cache."""
    return MockSessionCache()


@pytest.fixture
def manager(mock_ws_cache: MockSessionCache) -> ConnectionManager:
    """Create connection manager with mock cache."""
    return ConnectionManager(cache=mock_ws_cache)


class TestConnectionManager:
    """Connection manager tests."""

    @pytest.mark.asyncio
    async def test_connect_creates_connection(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Connect creates and stores connection."""
        websocket = MockWebSocket()

        connection = await manager.connect(websocket)
        assert connection.id is not None
        assert websocket.accepted
        assert manager.get_total_connections() == 1

    @pytest.mark.asyncio
    async def test_connect_with_user_id(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Connect with user ID sets authentication."""
        websocket = MockWebSocket()

        connection = await manager.connect(
            websocket,
            user_id="test-user",
        )

        assert connection.user_id == "test-user"
        assert connection.authenticated

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Disconnect removes connection from manager."""
        websocket = MockWebSocket()
        connection = await manager.connect(websocket)
        await manager.disconnect(connection)

        assert manager.get_total_connections() == 0

    @pytest.mark.asyncio
    async def test_subscribe_to_session(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Subscribe adds connection to session."""
        websocket = MockWebSocket()
        session_id = uuid4()
        connection = await manager.connect(websocket)
        await manager.subscribe_to_session(connection, session_id)

        assert connection.session_id == session_id
        assert manager.get_session_connection_count(session_id) == 1

    @pytest.mark.asyncio
    async def test_send_message(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Send message delivers to connection."""
        websocket = MockWebSocket()
        connection = await manager.connect(websocket)

        message = WSMessage(
            type=WSMessageType.PONG,
            payload={"test": "data"},
        )

        success = await manager.send_message(connection, message)

        assert success
        assert len(websocket.messages_sent) == 1
        assert websocket.messages_sent[0]["type"] == "pong"

    @pytest.mark.asyncio
    async def test_broadcast_to_session(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Broadcast delivers to all session connections."""
        session_id = uuid4()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()

        conn1 = await manager.connect(ws1)
        conn2 = await manager.connect(ws2)

        await manager.subscribe_to_session(conn1, session_id)
        await manager.subscribe_to_session(conn2, session_id)

        message = WSMessage(
            type=WSMessageType.TASK_STARTED,
            payload={"task_id": str(uuid4())},
        )
        sent = await manager.broadcast_to_session(session_id, message)

        assert sent == 2
        assert len(ws1.messages_sent) == 1
        assert len(ws2.messages_sent) == 1

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_session(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Broadcast to session with no connections returns 0."""
        session_id = uuid4()
        message = WSMessage(type=WSMessageType.PONG)

        sent = await manager.broadcast_to_session(session_id, message)

        assert sent == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_from_session(
        self,
        manager: ConnectionManager,
    ) -> None:
        """Unsubscribe removes connection from session."""
        websocket = MockWebSocket()
        session_id = uuid4()
        connection = await manager.connect(websocket)
        await manager.subscribe_to_session(connection, session_id)

        await manager.unsubscribe_from_session(connection)

        assert connection.session_id is None
        assert manager.get_session_connection_count(session_id) == 0
