"""WebSocket module for real-time communication."""

from .handlers import WebSocketHandler
from .manager import ConnectionManager

__all__ = [
    "ConnectionManager",
    "WebSocketHandler",
]
