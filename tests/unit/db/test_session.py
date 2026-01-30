"""Tests for database session management."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.db.session import (
    DatabaseSessionManager,
    close_db,
    get_db_session,
    get_session_manager,
    init_db,
)


@pytest.fixture(autouse=True)
def reset_session_manager():
    """Reset global session manager before and after each test."""
    import agent.db.session as session_module

    original = session_module.session_manager
    session_module.session_manager = None
    yield
    session_module.session_manager = original


class TestDatabaseSessionManager:
    """Tests for DatabaseSessionManager class."""

    def test_init(self) -> None:
        """Test DatabaseSessionManager initialization."""
        with patch("agent.db.session.create_async_engine") as mock_engine:
            mock_engine.return_value = MagicMock()

            manager = DatabaseSessionManager(
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                pool_size=5,
                max_overflow=10,
            )

            assert manager.engine is not None
            assert manager.session_factory is not None
            mock_engine.assert_called_once()

    async def test_close(self) -> None:
        """Test closing database engine."""
        with patch("agent.db.session.create_async_engine") as mock_create_engine:
            mock_engine = AsyncMock()
            mock_create_engine.return_value = mock_engine

            manager = DatabaseSessionManager(
                database_url="postgresql+asyncpg://user:pass@localhost/db",
            )

            await manager.close()

            mock_engine.dispose.assert_called_once()

    async def test_get_session(self) -> None:
        """Test getting database session."""
        with patch("agent.db.session.create_async_engine") as mock_create_engine:
            mock_engine = MagicMock()
            mock_create_engine.return_value = mock_engine

            manager = DatabaseSessionManager(
                database_url="postgresql+asyncpg://user:pass@localhost/db",
            )

            # Mock session factory
            mock_session = AsyncMock()
            manager.session_factory = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=None),
                )
            )

            async for session in manager.get_session():
                assert session is mock_session

    async def test_create_all(self) -> None:
        """Test creating all tables."""
        with patch("agent.db.session.create_async_engine") as mock_create_engine:
            mock_engine = MagicMock()
            mock_conn = AsyncMock()
            mock_engine.begin = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_conn),
                    __aexit__=AsyncMock(return_value=None),
                )
            )
            mock_create_engine.return_value = mock_engine

            manager = DatabaseSessionManager(
                database_url="postgresql+asyncpg://user:pass@localhost/db",
            )

            await manager.create_all()

            mock_conn.run_sync.assert_called_once()

    async def test_drop_all(self) -> None:
        """Test dropping all tables."""
        with patch("agent.db.session.create_async_engine") as mock_create_engine:
            mock_engine = MagicMock()
            mock_conn = AsyncMock()
            mock_engine.begin = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_conn),
                    __aexit__=AsyncMock(return_value=None),
                )
            )
            mock_create_engine.return_value = mock_engine

            manager = DatabaseSessionManager(
                database_url="postgresql+asyncpg://user:pass@localhost/db",
            )

            await manager.drop_all()

            mock_conn.run_sync.assert_called_once()


class TestInitDb:
    """Tests for init_db function."""

    def test_init_db_success(self) -> None:
        """Test successful database initialization."""
        with patch("agent.db.session.DatabaseSessionManager") as MockManager:
            mock_manager = MagicMock()
            MockManager.return_value = mock_manager

            init_db("postgresql+asyncpg://user:pass@localhost/db")

            MockManager.assert_called_once_with("postgresql+asyncpg://user:pass@localhost/db")

    def test_init_db_already_initialized(self) -> None:
        """Test error when already initialized."""

        with patch("agent.db.session.DatabaseSessionManager") as MockManager:
            mock_manager = MagicMock()
            MockManager.return_value = mock_manager

            init_db("postgresql+asyncpg://user:pass@localhost/db")

            with pytest.raises(RuntimeError, match="already initialized"):
                init_db("postgresql+asyncpg://user:pass@localhost/db")


class TestCloseDb:
    """Tests for close_db function."""

    async def test_close_db_success(self) -> None:
        """Test successful database close."""
        import agent.db.session as session_module

        mock_manager = AsyncMock()
        session_module.session_manager = mock_manager

        await close_db()

        mock_manager.close.assert_called_once()
        assert session_module.session_manager is None

    async def test_close_db_not_initialized(self) -> None:
        """Test close when not initialized."""
        import agent.db.session as session_module

        session_module.session_manager = None

        # Should not raise
        await close_db()


class TestGetSessionManager:
    """Tests for get_session_manager function."""

    def test_get_session_manager_success(self) -> None:
        """Test getting session manager."""
        import agent.db.session as session_module

        mock_manager = MagicMock()
        session_module.session_manager = mock_manager

        result = get_session_manager()

        assert result is mock_manager

    def test_get_session_manager_not_initialized(self) -> None:
        """Test error when not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            get_session_manager()


class TestGetDbSession:
    """Tests for get_db_session function."""

    async def test_get_db_session(self) -> None:
        """Test getting database session via dependency."""
        import agent.db.session as session_module

        mock_session = AsyncMock()

        async def mock_gen():
            yield mock_session

        mock_manager = MagicMock()
        mock_manager.get_session = mock_gen
        session_module.session_manager = mock_manager

        async for session in get_db_session():
            assert session is mock_session
