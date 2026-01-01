"""Session service tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.api.exceptions import AccessDeniedError, InvalidStateError, NotFoundError
from agent.api.services.session_service import SessionService
from agent.db.models.enums import SessionStatus

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create mock session cache."""
    cache = MagicMock()
    cache.set_session_state = AsyncMock()
    cache.invalidate_session_state = AsyncMock()
    cache.invalidate_user_sessions = AsyncMock()
    cache.get_cached_context = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def session_service(mock_db: AsyncMock, mock_cache: MagicMock) -> SessionService:
    """Create session service with mocked dependencies."""
    return SessionService(mock_db, mock_cache)


class TestCreateSession:
    """Tests for create_session method."""

    @pytest.mark.asyncio
    async def test_creates_session_successfully(
        self,
        session_service: SessionService,
        mock_cache: MagicMock,
    ) -> None:
        """Creates session with correct parameters."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.ACTIVE.value
        mock_session.title = None
        mock_session.created_at = datetime.now(UTC)
        mock_session.updated_at = datetime.now(UTC)
        mock_session.total_input_tokens = 0
        mock_session.total_output_tokens = 0
        mock_session.total_cost_usd = 0
        mock_session.context_usage_ratio = 0.0

        with patch.object(
            session_service.session_repo,
            "create",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_session

            result = await session_service.create_session(user_id)

            mock_create.assert_called_once()
            mock_cache.set_session_state.assert_called_once()
            mock_cache.invalidate_user_sessions.assert_called_once_with(user_id)
            assert result.id == session_id


class TestGetSession:
    """Tests for get_session method."""

    @pytest.mark.asyncio
    async def test_returns_session_details(
        self,
        session_service: SessionService,
    ) -> None:
        """Returns session details with tasks."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.ACTIVE.value
        mock_session.title = None
        mock_session.created_at = datetime.now(UTC)
        mock_session.updated_at = datetime.now(UTC)
        mock_session.total_input_tokens = 50
        mock_session.total_output_tokens = 50
        mock_session.total_cost_usd = 0.01
        mock_session.context_usage_ratio = 0.1

        with (
            patch.object(
                session_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch.object(
                session_service.task_repo,
                "get_by_session_id",
                new_callable=AsyncMock,
            ) as mock_tasks,
        ):
            mock_get.return_value = mock_session
            mock_tasks.return_value = []

            result = await session_service.get_session(session_id, user_id)

            assert result.id == session_id
            assert result.tasks == []

    @pytest.mark.asyncio
    async def test_raises_not_found_when_session_missing(
        self,
        session_service: SessionService,
    ) -> None:
        """Raises NotFoundError when session doesn't exist."""
        session_id = uuid4()
        user_id = "user-123"

        with patch.object(
            session_service.session_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None

            with pytest.raises(NotFoundError):
                await session_service.get_session(session_id, user_id)

    @pytest.mark.asyncio
    async def test_raises_access_denied_for_other_user(
        self,
        session_service: SessionService,
    ) -> None:
        """Raises AccessDeniedError when user doesn't own session."""
        session_id = uuid4()

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = "other-user"

        with patch.object(
            session_service.session_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_session

            with pytest.raises(AccessDeniedError):
                await session_service.get_session(session_id, "user-123")


class TestListSessions:
    """Tests for list_sessions method."""

    @pytest.mark.asyncio
    async def test_returns_paginated_sessions(
        self,
        session_service: SessionService,
    ) -> None:
        """Returns paginated session list."""
        user_id = "user-123"

        mock_sessions = [
            MagicMock(
                id=uuid4(),
                user_id=user_id,
                status=SessionStatus.ACTIVE.value,
                title=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=0,
                context_usage_ratio=0.0,
            )
            for _ in range(3)
        ]

        with (
            patch.object(
                session_service.session_repo,
                "get_by_user_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch.object(
                session_service.task_repo,
                "get_by_session_id",
                new_callable=AsyncMock,
            ) as mock_tasks,
        ):
            mock_get.return_value = mock_sessions
            mock_tasks.return_value = []  # No tasks for sessions

            result = await session_service.list_sessions(user_id, limit=10)

            assert len(result.items) == 3
            assert result.has_more is False


class TestPauseSession:
    """Tests for pause_session method."""

    @pytest.mark.asyncio
    async def test_pauses_active_session(
        self,
        session_service: SessionService,
        mock_cache: MagicMock,
    ) -> None:
        """Pauses an active session successfully."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.ACTIVE.value

        mock_updated = MagicMock()
        mock_updated.id = session_id
        mock_updated.user_id = user_id
        mock_updated.status = SessionStatus.PAUSED.value
        mock_updated.title = None
        mock_updated.created_at = datetime.now(UTC)
        mock_updated.updated_at = datetime.now(UTC)
        mock_updated.total_input_tokens = 0
        mock_updated.total_output_tokens = 0
        mock_updated.total_cost_usd = 0
        mock_updated.context_usage_ratio = 0.0

        with (
            patch.object(
                session_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch.object(
                session_service.session_repo,
                "pause_session",
                new_callable=AsyncMock,
            ) as mock_pause,
        ):
            mock_get.return_value = mock_session
            mock_pause.return_value = mock_updated

            result = await session_service.pause_session(session_id, user_id)

            assert result.status == SessionStatus.PAUSED.value
            mock_cache.invalidate_session_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_invalid_state_when_not_active(
        self,
        session_service: SessionService,
    ) -> None:
        """Raises InvalidStateError when session is not active."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.PAUSED.value

        with patch.object(
            session_service.session_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_session

            with pytest.raises(InvalidStateError):
                await session_service.pause_session(session_id, user_id)


class TestResumeSession:
    """Tests for resume_session method."""

    @pytest.mark.asyncio
    async def test_resumes_paused_session(
        self,
        session_service: SessionService,
        mock_cache: MagicMock,
    ) -> None:
        """Resumes a paused session successfully."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.PAUSED.value

        mock_updated = MagicMock()
        mock_updated.id = session_id
        mock_updated.user_id = user_id
        mock_updated.status = SessionStatus.ACTIVE.value
        mock_updated.title = None
        mock_updated.created_at = datetime.now(UTC)
        mock_updated.updated_at = datetime.now(UTC)
        mock_updated.total_input_tokens = 0
        mock_updated.total_output_tokens = 0
        mock_updated.total_cost_usd = 0
        mock_updated.context_usage_ratio = 0.0

        with (
            patch.object(
                session_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch.object(
                session_service.session_repo,
                "update",
                new_callable=AsyncMock,
            ) as mock_update,
            patch.object(
                session_service.snapshot_repo,
                "get_latest_snapshot",
                new_callable=AsyncMock,
            ) as mock_snapshot,
        ):
            mock_get.return_value = mock_session
            mock_update.return_value = mock_updated
            mock_snapshot.return_value = None

            result, context = await session_service.resume_session(session_id, user_id)

            assert result.status == SessionStatus.ACTIVE.value
            assert context is None

    @pytest.mark.asyncio
    async def test_raises_invalid_state_when_not_paused(
        self,
        session_service: SessionService,
    ) -> None:
        """Raises InvalidStateError when session is not paused."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.ACTIVE.value

        with patch.object(
            session_service.session_repo,
            "get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_session

            with pytest.raises(InvalidStateError):
                await session_service.resume_session(session_id, user_id)


class TestCompleteSession:
    """Tests for complete_session method."""

    @pytest.mark.asyncio
    async def test_completes_active_session(
        self,
        session_service: SessionService,
    ) -> None:
        """Completes an active session successfully."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.ACTIVE.value

        mock_completed = MagicMock()
        mock_completed.id = session_id
        mock_completed.user_id = user_id
        mock_completed.status = SessionStatus.COMPLETED.value
        mock_completed.title = None
        mock_completed.created_at = datetime.now(UTC)
        mock_completed.updated_at = datetime.now(UTC)
        mock_completed.total_input_tokens = 0
        mock_completed.total_output_tokens = 0
        mock_completed.total_cost_usd = 0
        mock_completed.context_usage_ratio = 0.0

        with (
            patch.object(
                session_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch.object(
                session_service.session_repo,
                "close_session",
                new_callable=AsyncMock,
            ) as mock_close,
        ):
            mock_get.return_value = mock_session
            mock_close.return_value = mock_completed

            result = await session_service.complete_session(session_id, user_id)

            assert result.status == SessionStatus.COMPLETED.value


class TestDeleteSession:
    """Tests for delete_session method."""

    @pytest.mark.asyncio
    async def test_deletes_completed_session(
        self,
        session_service: SessionService,
    ) -> None:
        """Deletes a completed session successfully."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.COMPLETED.value

        with (
            patch.object(
                session_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch.object(
                session_service.session_repo,
                "delete",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            mock_get.return_value = mock_session
            mock_delete.return_value = True

            await session_service.delete_session(session_id, user_id)

            mock_delete.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_deletes_active_session(
        self,
        session_service: SessionService,
        mock_cache: MagicMock,
    ) -> None:
        """Deletes an active session (users can delete sessions in any state)."""
        session_id = uuid4()
        user_id = "user-123"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.status = SessionStatus.ACTIVE.value

        with (
            patch.object(
                session_service.session_repo,
                "get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch.object(
                session_service.session_repo,
                "delete",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            mock_get.return_value = mock_session
            mock_delete.return_value = True

            # Should not raise - users can delete sessions regardless of status
            await session_service.delete_session(session_id, user_id)

            mock_delete.assert_called_once_with(session_id)
            mock_cache.invalidate_session_state.assert_called_once()
