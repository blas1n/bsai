"""WebSocket router tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from bsai.api.routers.websocket import _get_manager


class TestGetManager:
    """Tests for _get_manager function."""

    def test_gets_manager_from_app_state(self) -> None:
        """Gets manager from websocket app state."""
        mock_websocket = MagicMock()
        mock_manager = MagicMock()
        mock_websocket.app.state.ws_manager = mock_manager

        result = _get_manager(mock_websocket)

        assert result is mock_manager


@pytest.fixture
def app_with_ws_manager(app: FastAPI) -> FastAPI:
    """Create app with WebSocket manager in state."""
    mock_manager = MagicMock()
    app.state.ws_manager = mock_manager
    return app


class TestWebSocketEndpoints:
    """Integration tests for WebSocket endpoints."""

    def test_ws_endpoint_accessible(self, app_with_ws_manager: FastAPI) -> None:
        """WebSocket endpoint is accessible."""
        routes = [getattr(route, "path", "") for route in app_with_ws_manager.routes]
        assert "/api/v1/ws" in routes or any("/ws" in r for r in routes)
