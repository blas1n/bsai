"""Tests for LangGraph checkpointer utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetCheckpointer:
    """Tests for get_checkpointer context manager."""

    @pytest.mark.asyncio
    async def test_returns_async_postgres_saver(self) -> None:
        """Test that get_checkpointer returns AsyncPostgresSaver."""
        from agent.graph.checkpointer import get_checkpointer

        with (
            patch("agent.graph.checkpointer.get_database_settings") as mock_get_settings,
            patch("agent.graph.checkpointer.AsyncPostgresSaver") as mock_saver_class,
        ):
            mock_settings = MagicMock()
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
            mock_get_settings.return_value = mock_settings

            mock_saver = MagicMock()
            mock_saver.__aenter__ = AsyncMock(return_value=mock_saver)
            mock_saver.__aexit__ = AsyncMock(return_value=None)
            mock_saver.setup = AsyncMock()

            mock_saver_class.from_conn_string = MagicMock(return_value=mock_saver)

            async with get_checkpointer() as saver:
                assert saver is mock_saver
                mock_saver.setup.assert_called_once()

    @pytest.mark.asyncio
    async def test_strips_asyncpg_from_url(self) -> None:
        """Test that asyncpg is stripped from database URL."""
        from agent.graph.checkpointer import get_checkpointer

        with (
            patch("agent.graph.checkpointer.get_database_settings") as mock_get_settings,
            patch("agent.graph.checkpointer.AsyncPostgresSaver") as mock_saver_class,
        ):
            mock_settings = MagicMock()
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
            mock_get_settings.return_value = mock_settings

            mock_saver = MagicMock()
            mock_saver.__aenter__ = AsyncMock(return_value=mock_saver)
            mock_saver.__aexit__ = AsyncMock(return_value=None)
            mock_saver.setup = AsyncMock()

            mock_saver_class.from_conn_string = MagicMock(return_value=mock_saver)

            async with get_checkpointer():
                pass

            # Check the URL passed to from_conn_string
            call_args = mock_saver_class.from_conn_string.call_args[0][0]
            assert "+asyncpg" not in call_args
            assert call_args == "postgresql://user:pass@localhost/db"

    @pytest.mark.asyncio
    async def test_calls_setup_on_saver(self) -> None:
        """Test that setup is called on the saver."""
        from agent.graph.checkpointer import get_checkpointer

        with (
            patch("agent.graph.checkpointer.get_database_settings") as mock_get_settings,
            patch("agent.graph.checkpointer.AsyncPostgresSaver") as mock_saver_class,
        ):
            mock_settings = MagicMock()
            mock_settings.database_url = "postgresql://user:pass@localhost/db"
            mock_get_settings.return_value = mock_settings

            mock_saver = MagicMock()
            mock_saver.__aenter__ = AsyncMock(return_value=mock_saver)
            mock_saver.__aexit__ = AsyncMock(return_value=None)
            mock_saver.setup = AsyncMock()

            mock_saver_class.from_conn_string = MagicMock(return_value=mock_saver)

            async with get_checkpointer():
                pass

            mock_saver.setup.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_url_without_asyncpg(self) -> None:
        """Test handling URL that doesn't have asyncpg."""
        from agent.graph.checkpointer import get_checkpointer

        with (
            patch("agent.graph.checkpointer.get_database_settings") as mock_get_settings,
            patch("agent.graph.checkpointer.AsyncPostgresSaver") as mock_saver_class,
        ):
            mock_settings = MagicMock()
            # URL without asyncpg
            mock_settings.database_url = "postgresql://user:pass@localhost/db"
            mock_get_settings.return_value = mock_settings

            mock_saver = MagicMock()
            mock_saver.__aenter__ = AsyncMock(return_value=mock_saver)
            mock_saver.__aexit__ = AsyncMock(return_value=None)
            mock_saver.setup = AsyncMock()

            mock_saver_class.from_conn_string = MagicMock(return_value=mock_saver)

            async with get_checkpointer():
                pass

            # URL should remain unchanged
            call_args = mock_saver_class.from_conn_string.call_args[0][0]
            assert call_args == "postgresql://user:pass@localhost/db"
