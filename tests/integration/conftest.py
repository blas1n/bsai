"""Integration test fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def db_session() -> AsyncMock:
    """Create mock database session for integration tests.

    Note: For true integration tests with database, install aiosqlite:
        pip install aiosqlite

    Returns:
        Mock AsyncSession
    """
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()

    # Create mock execute that returns a mock result with scalars()
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    session.execute = AsyncMock(return_value=mock_result)

    session.refresh = AsyncMock()
    return session
