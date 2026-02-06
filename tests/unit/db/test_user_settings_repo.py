"""Tests for UserSettingsRepository."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from bsai.db.repository.user_settings_repo import UserSettingsRepository


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def repo(mock_session: AsyncMock) -> UserSettingsRepository:
    """Create UserSettingsRepository instance."""
    return UserSettingsRepository(mock_session)


class TestGetByUserId:
    """Tests for get_by_user_id method."""

    async def test_get_by_user_id_found(
        self,
        repo: UserSettingsRepository,
        mock_session: AsyncMock,
    ):
        """Test getting settings when user exists."""
        mock_settings = MagicMock()
        mock_settings.user_id = "test-user"
        mock_settings.theme = "dark"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_settings
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_user_id("test-user")

        assert result is not None
        assert result.user_id == "test-user"
        mock_session.execute.assert_called_once()

    async def test_get_by_user_id_not_found(
        self,
        repo: UserSettingsRepository,
        mock_session: AsyncMock,
    ):
        """Test getting settings when user doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_user_id("nonexistent-user")

        assert result is None


class TestGetOrCreate:
    """Tests for get_or_create method."""

    async def test_get_or_create_existing(
        self,
        repo: UserSettingsRepository,
        mock_session: AsyncMock,
    ):
        """Test get_or_create when settings exist."""
        mock_settings = MagicMock()
        mock_settings.user_id = "test-user"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_settings
        mock_session.execute.return_value = mock_result

        result = await repo.get_or_create("test-user")

        assert result is not None
        assert result.user_id == "test-user"
        # Should not call add since settings exist
        mock_session.add.assert_not_called()

    async def test_get_or_create_new(
        self,
        repo: UserSettingsRepository,
        mock_session: AsyncMock,
    ):
        """Test get_or_create when settings don't exist."""
        # First call returns None (not found)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Mock create behavior
        created_settings = MagicMock()
        created_settings.user_id = "new-user"

        def mock_refresh(obj):
            obj.user_id = "new-user"

        mock_session.refresh.side_effect = mock_refresh

        result = await repo.get_or_create("new-user")

        assert result is not None
        mock_session.add.assert_called_once()
        # flush is called twice: once by create() in BaseRepository, once by get_or_create()
        assert mock_session.flush.await_count == 2


class TestUpdatePreferences:
    """Tests for update_preferences method."""

    async def test_update_preferences_success(
        self,
        repo: UserSettingsRepository,
        mock_session: AsyncMock,
    ):
        """Test updating user preferences."""
        mock_settings = MagicMock()
        mock_settings.user_id = "test-user"
        mock_settings.theme = "light"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_settings
        mock_session.execute.return_value = mock_result

        result = await repo.update_preferences("test-user", theme="dark")

        assert result is not None
        assert mock_settings.theme == "dark"
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once()

    async def test_update_preferences_not_found(
        self,
        repo: UserSettingsRepository,
        mock_session: AsyncMock,
    ):
        """Test updating preferences when user doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.update_preferences("nonexistent-user", theme="dark")

        assert result is None
        mock_session.flush.assert_not_called()

    async def test_update_preferences_invalid_field(
        self,
        repo: UserSettingsRepository,
        mock_session: AsyncMock,
    ):
        """Test updating with invalid field name."""
        mock_settings = MagicMock()
        mock_settings.user_id = "test-user"
        # hasattr will return False for invalid_field
        mock_settings.configure_mock(**{"invalid_field": None})
        delattr(mock_settings, "invalid_field")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_settings
        mock_session.execute.return_value = mock_result

        result = await repo.update_preferences("test-user", invalid_field="value")

        assert result is not None
        # invalid_field should not be set
        mock_session.flush.assert_called_once()

    async def test_update_preferences_multiple_fields(
        self,
        repo: UserSettingsRepository,
        mock_session: AsyncMock,
    ):
        """Test updating multiple preferences at once."""
        mock_settings = MagicMock()
        mock_settings.user_id = "test-user"
        mock_settings.theme = "light"
        mock_settings.language = "en"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_settings
        mock_session.execute.return_value = mock_result

        result = await repo.update_preferences(
            "test-user",
            theme="dark",
            language="ko",
        )

        assert result is not None
        assert mock_settings.theme == "dark"
        assert mock_settings.language == "ko"
