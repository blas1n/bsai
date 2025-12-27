"""WebSocket endpoint for real-time streaming."""

from uuid import UUID

from fastapi import APIRouter, Query, WebSocket

from ..dependencies import get_cache
from ..websocket import ConnectionManager, WebSocketHandler

router = APIRouter(tags=["websocket"])

# Global connection manager instance
_manager: ConnectionManager | None = None


def get_ws_manager() -> ConnectionManager:
    """Get or create the WebSocket connection manager.

    Returns:
        ConnectionManager singleton
    """
    global _manager
    if _manager is None:
        cache = get_cache()
        _manager = ConnectionManager(cache=cache)
    return _manager


def set_ws_manager(manager: ConnectionManager) -> None:
    """Set the WebSocket connection manager (for testing).

    Args:
        manager: Manager instance to use
    """
    global _manager
    _manager = manager


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    session_id: UUID | None = Query(default=None),
) -> None:
    """WebSocket endpoint for real-time streaming.

    Connect to receive real-time updates for tasks and LLM streaming.

    Authentication:
        - Via query parameter: ?token=<jwt>
        - Or via first message: {"type": "auth", "payload": {"token": "<jwt>"}}

    Session Subscription:
        - Via query parameter: ?session_id=<uuid>
        - Or via message: {"type": "subscribe", "payload": {"session_id": "<uuid>"}}

    Message Types (Client -> Server):
        - auth: Authenticate with JWT
        - subscribe: Subscribe to session updates
        - unsubscribe: Unsubscribe from session
        - ping: Keep-alive ping

    Message Types (Server -> Client):
        - auth_success: Authentication successful
        - subscribed: Session subscription confirmed
        - pong: Keep-alive response
        - task_started: Task execution started
        - task_progress: Task progress update
        - task_completed: Task completed successfully
        - task_failed: Task execution failed
        - llm_chunk: LLM streaming chunk
        - llm_complete: LLM streaming complete
        - error: Error message

    Args:
        websocket: WebSocket connection
        token: Optional JWT token for authentication
        session_id: Optional session ID to auto-subscribe
    """
    manager = get_ws_manager()
    handler = WebSocketHandler(manager=manager, cache=manager.cache)

    await handler.handle_connection(
        websocket=websocket,
        session_id=session_id,
        token=token,
    )


@router.websocket("/ws/{session_id}")
async def websocket_session_endpoint(
    websocket: WebSocket,
    session_id: UUID,
    token: str | None = Query(default=None),
) -> None:
    """WebSocket endpoint for a specific session.

    Convenience endpoint that auto-subscribes to the specified session.

    Args:
        websocket: WebSocket connection
        session_id: Session ID to subscribe to
        token: Optional JWT token for authentication
    """
    manager = get_ws_manager()
    handler = WebSocketHandler(manager=manager, cache=manager.cache)

    await handler.handle_connection(
        websocket=websocket,
        session_id=session_id,
        token=token,
    )
