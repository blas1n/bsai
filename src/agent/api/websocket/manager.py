"""WebSocket connection manager for real-time streaming."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID, uuid4

import structlog
from fastapi import WebSocketDisconnect

from ..schemas import WSMessage


class WebSocketProtocol(Protocol):
    """Protocol for WebSocket connections."""

    async def accept(self) -> None:
        """Accept the WebSocket connection."""
        ...

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the WebSocket connection."""
        ...

    async def send_json(self, data: dict[str, Any]) -> None:
        """Send JSON data over the WebSocket."""
        ...

    async def receive_json(self) -> dict[str, Any]:
        """Receive JSON data from the WebSocket."""
        ...


class SessionCacheProtocol(Protocol):
    """Protocol for session cache used by ConnectionManager."""

    async def register_ws_connection(
        self,
        session_id: UUID,
        connection_id: str,
    ) -> None:
        """Register WebSocket connection."""
        ...

    async def unregister_ws_connection(
        self,
        session_id: UUID,
        connection_id: str,
    ) -> None:
        """Unregister WebSocket connection."""
        ...


class McpToolExecutorProtocol(Protocol):
    """Protocol for MCP tool executor to avoid circular imports."""

    user_id: str
    session_id: UUID

    def handle_stdio_response(
        self,
        request_id: str,
        success: bool,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        execution_time_ms: int | None = None,
    ) -> None:
        """Handle stdio tool execution response from frontend."""

    def handle_approval_response(
        self,
        request_id: str,
        approved: bool,
    ) -> None:
        """Handle user approval response from frontend."""


logger = structlog.get_logger()


@dataclass
class Connection:
    """Represents a WebSocket connection."""

    id: str
    websocket: WebSocketProtocol
    session_id: UUID | None = None
    user_id: str | None = None
    authenticated: bool = False


@dataclass
class ConnectionManager:
    """Manages WebSocket connections and message broadcasting.

    Handles connection lifecycle, session subscriptions, and
    message routing for real-time streaming.

    Also manages MCP tool executors for each session.
    """

    cache: SessionCacheProtocol
    _connections: dict[str, Connection] = field(default_factory=dict)
    _session_connections: dict[UUID, set[str]] = field(default_factory=dict)
    _mcp_executors: dict[UUID, McpToolExecutorProtocol] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def connect(
        self,
        websocket: WebSocketProtocol,
        user_id: str | None = None,
    ) -> Connection:
        """Accept a new WebSocket connection.

        Args:
            websocket: WebSocket connection
            user_id: Optional authenticated user ID

        Returns:
            Connection object
        """
        await websocket.accept()

        connection_id = str(uuid4())
        connection = Connection(
            id=connection_id,
            websocket=websocket,
            user_id=user_id,
            authenticated=user_id is not None,
        )

        async with self._lock:
            self._connections[connection_id] = connection

        logger.info(
            "ws_connected",
            connection_id=connection_id,
            authenticated=connection.authenticated,
        )

        return connection

    async def disconnect(self, connection: Connection) -> None:
        """Handle connection disconnect.

        Args:
            connection: Connection to remove
        """
        async with self._lock:
            # Remove from connections
            self._connections.pop(connection.id, None)

            # Remove from session subscriptions
            if connection.session_id:
                session_conns = self._session_connections.get(connection.session_id)
                if session_conns:
                    session_conns.discard(connection.id)
                    if not session_conns:
                        del self._session_connections[connection.session_id]

                # Update cache
                await self.cache.unregister_ws_connection(
                    connection.session_id,
                    connection.id,
                )

        logger.info(
            "ws_disconnected",
            connection_id=connection.id,
            session_id=str(connection.session_id) if connection.session_id else None,
        )

    async def subscribe_to_session(
        self,
        connection: Connection,
        session_id: UUID,
    ) -> None:
        """Subscribe connection to session updates.

        Args:
            connection: Connection to subscribe
            session_id: Session to subscribe to
        """
        async with self._lock:
            # Unsubscribe from previous session if any
            if connection.session_id:
                old_conns = self._session_connections.get(connection.session_id)
                if old_conns:
                    old_conns.discard(connection.id)
                    if not old_conns:
                        del self._session_connections[connection.session_id]
                await self.cache.unregister_ws_connection(
                    connection.session_id,
                    connection.id,
                )

            # Subscribe to new session
            connection.session_id = session_id
            if session_id not in self._session_connections:
                self._session_connections[session_id] = set()
            self._session_connections[session_id].add(connection.id)

            # Update cache
            await self.cache.register_ws_connection(session_id, connection.id)

        logger.info(
            "ws_subscribed",
            connection_id=connection.id,
            session_id=str(session_id),
        )

    async def unsubscribe_from_session(
        self,
        connection: Connection,
    ) -> None:
        """Unsubscribe connection from current session.

        Args:
            connection: Connection to unsubscribe
        """
        if not connection.session_id:
            return

        async with self._lock:
            session_conns = self._session_connections.get(connection.session_id)
            if session_conns:
                session_conns.discard(connection.id)
                if not session_conns:
                    del self._session_connections[connection.session_id]

            await self.cache.unregister_ws_connection(
                connection.session_id,
                connection.id,
            )

            old_session = connection.session_id
            connection.session_id = None

        logger.info(
            "ws_unsubscribed",
            connection_id=connection.id,
            session_id=str(old_session),
        )

    async def send_message(
        self,
        connection: Connection,
        message: WSMessage,
    ) -> bool:
        """Send message to a specific connection.

        Args:
            connection: Target connection
            message: Message to send

        Returns:
            True if sent successfully
        """
        try:
            await connection.websocket.send_json(message.model_dump(mode="json"))
            return True
        except WebSocketDisconnect:
            await self.disconnect(connection)
            return False
        except Exception as e:
            logger.error(
                "ws_send_failed",
                connection_id=connection.id,
                error=str(e),
            )
            return False

    async def broadcast_to_session(
        self,
        session_id: UUID,
        message: WSMessage,
    ) -> int:
        """Broadcast message to all connections subscribed to a session.

        Args:
            session_id: Target session
            message: Message to broadcast

        Returns:
            Number of connections message was sent to
        """
        async with self._lock:
            connection_ids = self._session_connections.get(session_id, set()).copy()

        if not connection_ids:
            logger.warning(
                "ws_broadcast_no_connections",
                session_id=str(session_id),
                message_type=message.type,
            )
            return 0

        sent_count = 0
        failed_connections: list[Connection] = []

        for conn_id in connection_ids:
            connection = self._connections.get(conn_id)
            if connection:
                try:
                    await connection.websocket.send_json(message.model_dump(mode="json"))
                    sent_count += 1
                except WebSocketDisconnect:
                    failed_connections.append(connection)
                except Exception as e:
                    logger.error(
                        "ws_broadcast_failed",
                        connection_id=conn_id,
                        error=str(e),
                    )
                    failed_connections.append(connection)

        # Clean up failed connections
        for conn in failed_connections:
            await self.disconnect(conn)

        logger.debug(
            "ws_broadcast_complete",
            session_id=str(session_id),
            sent_count=sent_count,
            failed_count=len(failed_connections),
        )

        return sent_count

    async def broadcast_to_user(
        self,
        user_id: str,
        message: WSMessage,
    ) -> int:
        """Broadcast message to all connections for a user.

        Args:
            user_id: Target user
            message: Message to broadcast

        Returns:
            Number of connections message was sent to
        """
        async with self._lock:
            user_connections = [
                conn for conn in self._connections.values() if conn.user_id == user_id
            ]

        if not user_connections:
            return 0

        sent_count = 0
        for connection in user_connections:
            if await self.send_message(connection, message):
                sent_count += 1

        return sent_count

    def get_session_connection_count(self, session_id: UUID) -> int:
        """Get number of connections for a session.

        Args:
            session_id: Session ID

        Returns:
            Number of active connections
        """
        return len(self._session_connections.get(session_id, set()))

    def get_total_connections(self) -> int:
        """Get total number of active connections.

        Returns:
            Total connection count
        """
        return len(self._connections)

    def register_mcp_executor(
        self,
        session_id: UUID,
        executor: McpToolExecutorProtocol,
    ) -> None:
        """Register MCP tool executor for a session.

        Args:
            session_id: Session ID
            executor: MCP tool executor instance
        """
        self._mcp_executors[session_id] = executor
        logger.debug("mcp_executor_registered", session_id=str(session_id))

    def get_mcp_executor(self, session_id: UUID) -> McpToolExecutorProtocol | None:
        """Get MCP tool executor for a session.

        Args:
            session_id: Session ID

        Returns:
            Executor if found, None otherwise
        """
        return self._mcp_executors.get(session_id)

    def unregister_mcp_executor(self, session_id: UUID) -> None:
        """Unregister MCP tool executor for a session.

        Args:
            session_id: Session ID
        """
        executor = self._mcp_executors.pop(session_id, None)
        if executor:
            logger.debug("mcp_executor_unregistered", session_id=str(session_id))
