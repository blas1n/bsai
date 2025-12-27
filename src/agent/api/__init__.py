"""FastAPI application module.

Provides REST API, WebSocket streaming, and authentication.
"""

from .main import create_app

__all__ = ["create_app"]
