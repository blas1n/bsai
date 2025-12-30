"""Memory snapshot repository tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.repository.memory_snapshot_repo import MemorySnapshotRepository

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def snapshot_repo(mock_session: AsyncMock) -> MemorySnapshotRepository:
    """Create memory snapshot repository."""
    return MemorySnapshotRepository(mock_session)


class TestGetLatestSnapshot:
    """Tests for get_latest_snapshot method."""

    @pytest.mark.asyncio
    async def test_returns_latest_snapshot(
        self,
        snapshot_repo: MemorySnapshotRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns most recent snapshot for session."""
        session_id = uuid4()

        mock_snapshot = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_snapshot
        mock_session.execute.return_value = mock_result

        result = await snapshot_repo.get_latest_snapshot(session_id)

        assert result is mock_snapshot
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_snapshots(
        self,
        snapshot_repo: MemorySnapshotRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns None when session has no snapshots."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await snapshot_repo.get_latest_snapshot(session_id)

        assert result is None


class TestGetBySession:
    """Tests for get_by_session method."""

    @pytest.mark.asyncio
    async def test_returns_snapshots_for_session(
        self,
        snapshot_repo: MemorySnapshotRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns snapshots for given session."""
        session_id = uuid4()

        mock_snapshots = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_snapshots
        mock_session.execute.return_value = mock_result

        result = await snapshot_repo.get_by_session(session_id)

        assert result == mock_snapshots
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_applies_limit(
        self,
        snapshot_repo: MemorySnapshotRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Applies limit parameter."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await snapshot_repo.get_by_session(session_id, limit=5)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_snapshots(
        self,
        snapshot_repo: MemorySnapshotRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when session has no snapshots."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await snapshot_repo.get_by_session(session_id)

        assert result == []


class TestGetByType:
    """Tests for get_by_type method."""

    @pytest.mark.asyncio
    async def test_returns_snapshots_by_type(
        self,
        snapshot_repo: MemorySnapshotRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns snapshots filtered by type."""
        session_id = uuid4()

        mock_snapshots = [MagicMock(snapshot_type="manual")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_snapshots
        mock_session.execute.return_value = mock_result

        result = await snapshot_repo.get_by_type(session_id, "manual")

        assert result == mock_snapshots

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_type_matches(
        self,
        snapshot_repo: MemorySnapshotRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when no snapshots match type."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await snapshot_repo.get_by_type(session_id, "auto")

        assert result == []
