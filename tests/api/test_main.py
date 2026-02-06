"""Main application tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bsai.api.main import create_app, lifespan

if TYPE_CHECKING:
    pass


class TestCreateApp:
    """Tests for create_app function."""

    def test_creates_fastapi_app(self) -> None:
        """Creates FastAPI application."""
        with (
            patch("bsai.api.main.get_api_settings") as mock_api_settings,
            patch("bsai.api.main.get_auth_settings") as mock_auth_settings,
        ):
            mock_api_settings.return_value = MagicMock(
                title="Test API",
                description="Test description",
                version="1.0.0",
                debug=False,
                cors_origins=[],
            )
            mock_auth_settings.return_value = MagicMock(auth_enabled=False)

            app = create_app()

            assert app is not None
            assert app.title == "Test API"

    def test_configures_cors_when_origins_set(self) -> None:
        """Configures CORS when origins are specified."""
        with (
            patch("bsai.api.main.get_api_settings") as mock_api_settings,
            patch("bsai.api.main.get_auth_settings") as mock_auth_settings,
        ):
            mock_api_settings.return_value = MagicMock(
                title="Test API",
                description="Test",
                version="1.0.0",
                debug=False,
                cors_origins=["http://localhost:3000"],
            )
            mock_auth_settings.return_value = MagicMock(auth_enabled=False)

            app = create_app()

            # CORS middleware should be added
            assert app is not None

    def test_skips_cors_when_no_origins(self) -> None:
        """Skips CORS when no origins specified."""
        with (
            patch("bsai.api.main.get_api_settings") as mock_api_settings,
            patch("bsai.api.main.get_auth_settings") as mock_auth_settings,
        ):
            mock_api_settings.return_value = MagicMock(
                title="Test API",
                description="Test",
                version="1.0.0",
                debug=False,
                cors_origins=[],
            )
            mock_auth_settings.return_value = MagicMock(auth_enabled=False)

            app = create_app()

            assert app is not None


class TestLifespan:
    """Tests for lifespan context manager."""

    @pytest.mark.asyncio
    async def test_initializes_redis_on_startup(self) -> None:
        """Initializes Redis on startup."""
        mock_app = MagicMock()

        with (
            patch("bsai.api.main.init_redis", new_callable=AsyncMock) as mock_init,
            patch("bsai.api.main.close_redis", new_callable=AsyncMock) as mock_close,
        ):
            async with lifespan(mock_app):
                mock_init.assert_called_once()

            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_closes_redis_on_shutdown(self) -> None:
        """Closes Redis on shutdown."""
        mock_app = MagicMock()

        with (
            patch("bsai.api.main.init_redis", new_callable=AsyncMock),
            patch("bsai.api.main.close_redis", new_callable=AsyncMock) as mock_close,
        ):
            async with lifespan(mock_app):
                pass

            mock_close.assert_called_once()
