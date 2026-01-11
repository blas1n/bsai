"""WebSocket message handlers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from agent.cache import SessionCache
from agent.db.repository.session_repo import SessionRepository
from agent.db.session import get_db_session

from ..auth import authenticate_websocket
from ..schemas import (
    WSMessage,
    WSMessageType,
)
from .manager import Connection, ConnectionManager

logger = structlog.get_logger()


class WebSocketHandler:
    """Handles WebSocket message processing.

    Manages authentication, message routing, and session subscriptions.
    """

    def __init__(
        self,
        manager: ConnectionManager,
        cache: SessionCache,
    ) -> None:
        """Initialize handler.

        Args:
            manager: Connection manager
            cache: Session cache
        """
        self.manager = manager
        self.cache = cache

    async def handle_connection(
        self,
        websocket: WebSocket,
        session_id: UUID | None = None,
        token: str | None = None,
    ) -> None:
        """Handle a WebSocket connection lifecycle.

        Args:
            websocket: WebSocket connection
            session_id: Optional session to auto-subscribe
            token: Optional auth token from query param
        """
        # Authenticate if token provided
        user_id = None
        if token:
            try:
                user_id = await authenticate_websocket(token)
            except Exception as e:
                logger.warning("ws_auth_failed", error=str(e))
                await websocket.close(code=4001, reason="Authentication failed")
                return

        # Accept connection
        connection = await self.manager.connect(websocket, user_id)

        try:
            # Auto-subscribe to session if provided
            if session_id and connection.authenticated:
                await self.manager.subscribe_to_session(connection, session_id)
                await self._send_auth_success(connection)

            # Handle messages
            await self._message_loop(connection)

        except WebSocketDisconnect:
            logger.debug("ws_client_disconnected", connection_id=str(connection.id))
        except Exception as e:
            logger.exception("ws_handler_error", error=str(e))
        finally:
            await self.manager.disconnect(connection)

    async def _message_loop(self, connection: Connection) -> None:
        """Process incoming messages.

        Args:
            connection: Active connection
        """
        while True:
            try:
                data = await connection.websocket.receive_json()
                await self._handle_message(connection, data)
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.error(
                    "ws_message_error",
                    connection_id=connection.id,
                    error=str(e),
                )
                await self._send_error(connection, str(e))

    async def _handle_message(
        self,
        connection: Connection,
        data: dict[str, Any],
    ) -> None:
        """Route and handle a single message.

        Args:
            connection: Source connection
            data: Message data
        """
        msg_type = data.get("type")

        if msg_type == WSMessageType.AUTH:
            await self._handle_auth(connection, data)
        elif msg_type == WSMessageType.SUBSCRIBE:
            await self._handle_subscribe(connection, data)
        elif msg_type == WSMessageType.PING:
            await self._handle_ping(connection)
        elif msg_type == WSMessageType.MCP_TOOL_CALL_RESPONSE:
            await self._handle_mcp_tool_response(connection, data)
        elif msg_type == WSMessageType.MCP_APPROVAL_RESPONSE:
            await self._handle_mcp_approval_response(connection, data)
        else:
            logger.warning(
                "ws_unknown_message",
                connection_id=connection.id,
                type=msg_type,
            )

    async def _handle_auth(
        self,
        connection: Connection,
        data: dict[str, Any],
    ) -> None:
        """Handle authentication message.

        Args:
            connection: Source connection
            data: Auth message data
        """
        token = data.get("payload", {}).get("token")
        if not token:
            await self._send_error(connection, "Token required")
            return

        try:
            user_id = await authenticate_websocket(token)
            connection.user_id = user_id
            connection.authenticated = True

            await self._send_auth_success(connection)

            logger.info(
                "ws_authenticated",
                connection_id=connection.id,
                user_id=connection.user_id,
            )

        except Exception as e:
            logger.warning(
                "ws_auth_failed",
                connection_id=connection.id,
                error=str(e),
            )
            await self._send_error(connection, "Authentication failed")

    async def _handle_subscribe(
        self,
        connection: Connection,
        data: dict[str, Any],
    ) -> None:
        """Handle session subscription message.

        Args:
            connection: Source connection
            data: Subscribe message data
        """
        if not connection.authenticated:
            await self._send_error(connection, "Authentication required")
            return

        session_id_str = data.get("payload", {}).get("session_id")
        if not session_id_str:
            await self._send_error(connection, "session_id required")
            return

        try:
            session_id = UUID(session_id_str)
        except ValueError:
            await self._send_error(connection, "Invalid session_id")
            return

        # Verify user owns the session before allowing subscription
        if connection.user_id:
            async for db in get_db_session():
                repo = SessionRepository(db)
                is_owner = await repo.verify_ownership(session_id, connection.user_id)
                if not is_owner:
                    logger.warning(
                        "ws_subscribe_unauthorized",
                        connection_id=connection.id,
                        user_id=connection.user_id,
                        session_id=str(session_id),
                    )
                    await self._send_error(connection, "Not authorized to access this session")
                    return
                break

        await self.manager.subscribe_to_session(connection, session_id)

        await self.manager.send_message(
            connection,
            WSMessage(
                type=WSMessageType.SUBSCRIBED,
                payload={"session_id": str(session_id)},
            ),
        )

    async def _handle_ping(self, connection: Connection) -> None:
        """Handle ping message.

        Args:
            connection: Source connection
        """
        await self.manager.send_message(
            connection,
            WSMessage(type=WSMessageType.PONG),
        )

    async def _send_auth_success(self, connection: Connection) -> None:
        """Send authentication success message.

        Args:
            connection: Target connection
        """
        await self.manager.send_message(
            connection,
            WSMessage(
                type=WSMessageType.AUTH_SUCCESS,
                payload={"user_id": connection.user_id},
            ),
        )

    async def _send_error(self, connection: Connection, message: str) -> None:
        """Send error message.

        Args:
            connection: Target connection
            message: Error message
        """
        await self.manager.send_message(
            connection,
            WSMessage(
                type=WSMessageType.ERROR,
                payload={"error": message},
            ),
        )

    async def _handle_mcp_tool_response(
        self,
        connection: Connection,
        data: dict[str, Any],
    ) -> None:
        """Handle MCP tool call response from frontend.

        This is called when frontend completes stdio tool execution.

        Args:
            connection: Source connection
            data: Tool response data
        """
        if not connection.authenticated:
            await self._send_error(connection, "Authentication required")
            return

        if not connection.session_id:
            await self._send_error(connection, "No session subscribed")
            return

        payload = data.get("payload", {})
        request_id = payload.get("request_id")

        if not request_id:
            logger.warning(
                "mcp_tool_response_missing_request_id",
                connection_id=connection.id,
            )
            return

        # Get executor for this session from ConnectionManager
        executor = self.manager.get_mcp_executor(connection.session_id)
        if not executor:
            logger.warning(
                "mcp_tool_response_no_executor",
                connection_id=connection.id,
                session_id=str(connection.session_id),
                request_id=request_id,
            )
            return

        # Forward to executor - it will resolve the pending asyncio.Future
        executor.handle_stdio_response(
            request_id=request_id,
            success=payload.get("success", False),
            output=payload.get("output"),
            error=payload.get("error"),
            execution_time_ms=payload.get("execution_time_ms"),
        )

        logger.info(
            "mcp_tool_response_handled",
            connection_id=connection.id,
            session_id=str(connection.session_id),
            request_id=request_id,
            success=payload.get("success"),
        )

    async def _handle_mcp_approval_response(
        self,
        connection: Connection,
        data: dict[str, Any],
    ) -> None:
        """Handle MCP approval response from user.

        Args:
            connection: Source connection
            data: Approval response data
        """
        if not connection.authenticated:
            await self._send_error(connection, "Authentication required")
            return

        if not connection.session_id:
            await self._send_error(connection, "No session subscribed")
            return

        payload = data.get("payload", {})
        request_id = payload.get("request_id")
        approved = payload.get("approved", False)

        if not request_id:
            logger.warning(
                "mcp_approval_response_missing_request_id",
                connection_id=connection.id,
            )
            return

        # Get executor for this session from ConnectionManager
        executor = self.manager.get_mcp_executor(connection.session_id)
        if not executor:
            logger.warning(
                "mcp_approval_response_no_executor",
                connection_id=connection.id,
                session_id=str(connection.session_id),
                request_id=request_id,
            )
            return

        # Forward to executor - it will resolve the pending asyncio.Future
        executor.handle_approval_response(
            request_id=request_id,
            approved=approved,
        )

        logger.info(
            "mcp_approval_response_handled",
            connection_id=connection.id,
            session_id=str(connection.session_id),
            request_id=request_id,
            approved=approved,
        )
