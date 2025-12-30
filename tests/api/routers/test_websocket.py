"""WebSocket router tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, patch

from agent.api.routers.websocket import (
    get_ws_manager,
    set_ws_manager,
)

if TYPE_CHECKING:
    from agent.api.websocket.manager import ConnectionManager


def clear_ws_manager() -> None:
    """Clear the WebSocket manager for test cleanup."""
    set_ws_manager(cast("ConnectionManager", None))


class TestGetWsManager:
    """Tests for get_ws_manager function."""

    def test_creates_manager_when_none(self) -> None:
        """Creates new manager when none exists."""
        # Reset global state
        clear_ws_manager()

        with patch("agent.api.routers.websocket.get_cache") as mock_get_cache:
            mock_cache = MagicMock()
            mock_get_cache.return_value = mock_cache

            with patch("agent.api.routers.websocket.ConnectionManager") as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager_class.return_value = mock_manager

                result = get_ws_manager()

                mock_manager_class.assert_called_once_with(cache=mock_cache)
                assert result is mock_manager

        # Clean up
        clear_ws_manager()

    def test_returns_existing_manager(self) -> None:
        """Returns existing manager when one exists."""
        mock_manager = MagicMock()
        set_ws_manager(cast("ConnectionManager", mock_manager))

        result = get_ws_manager()

        assert result is mock_manager

        # Clean up
        clear_ws_manager()


class TestSetWsManager:
    """Tests for set_ws_manager function."""

    def test_sets_manager(self) -> None:
        """Sets the global manager."""
        mock_manager = MagicMock()

        set_ws_manager(cast("ConnectionManager", mock_manager))

        assert get_ws_manager() is mock_manager

        # Clean up
        clear_ws_manager()

    def test_clears_manager_with_none(self) -> None:
        """Clears manager when set to None."""
        mock_manager = MagicMock()
        set_ws_manager(cast("ConnectionManager", mock_manager))

        clear_ws_manager()

        # Next call should create new manager
        with patch("agent.api.routers.websocket.get_cache") as mock_get_cache:
            mock_cache = MagicMock()
            mock_get_cache.return_value = mock_cache

            with patch("agent.api.routers.websocket.ConnectionManager") as mock_manager_class:
                mock_manager_class.return_value = MagicMock()
                get_ws_manager()
                mock_manager_class.assert_called_once()

        # Clean up
        clear_ws_manager()
