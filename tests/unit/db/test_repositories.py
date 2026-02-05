"""Tests for repository layer."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.repository.session_repo import SessionRepository


class TestSessionRepository:
    """Tests for SessionRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create repository with mock session."""
        return SessionRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_by_user_id(self, repository, mock_session):
        """Test getting sessions by user ID."""
        user_id = "test-user-123"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_user_id(user_id)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_id_with_pagination(self, repository, mock_session):
        """Test getting sessions with limit and offset."""
        user_id = "test-user-123"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_user_id(user_id, limit=5, offset=10)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_active_sessions(self, repository, mock_session):
        """Test getting active sessions."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_active_sessions()

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_active_sessions_by_user(self, repository, mock_session):
        """Test getting active sessions filtered by user."""
        user_id = "test-user-123"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_active_sessions(user_id=user_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_update_tokens(self, repository, mock_session):
        """Test updating session token counts."""
        session_id = uuid4()
        mock_session_obj = MagicMock()
        mock_session_obj.total_input_tokens = 100
        mock_session_obj.total_output_tokens = 50

        # Mock get_by_id to return the session object
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_session.execute.return_value = mock_result

        result = await repository.update_tokens(session_id, 50, 25)

        assert result == mock_session_obj
        assert mock_session_obj.total_input_tokens == 150
        assert mock_session_obj.total_output_tokens == 75

    @pytest.mark.asyncio
    async def test_update_tokens_not_found(self, repository, mock_session):
        """Test updating tokens for non-existent session."""
        session_id = uuid4()

        # Mock get_by_id to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.update_tokens(session_id, 50, 25)

        assert result is None

    @pytest.mark.asyncio
    async def test_update_cost(self, repository, mock_session):
        """Test updating session cost."""
        session_id = uuid4()
        mock_session_obj = MagicMock()
        mock_session_obj.total_cost_usd = Decimal("1.50")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_session.execute.return_value = mock_result

        result = await repository.update_cost(session_id, Decimal("0.50"))

        assert result == mock_session_obj
        assert mock_session_obj.total_cost_usd == Decimal("2.00")

    @pytest.mark.asyncio
    async def test_update_cost_not_found(self, repository, mock_session):
        """Test updating cost for non-existent session."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.update_cost(session_id, Decimal("0.50"))

        assert result is None

    @pytest.mark.asyncio
    async def test_get_total_cost_by_user(self, repository, mock_session):
        """Test calculating total cost for user."""
        user_id = "test-user-123"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = Decimal("10.50")
        mock_session.execute.return_value = mock_result

        result = await repository.get_total_cost_by_user(user_id)

        assert result == Decimal("10.50")

    @pytest.mark.asyncio
    async def test_get_total_cost_by_user_no_sessions(self, repository, mock_session):
        """Test total cost when user has no sessions."""
        user_id = "test-user-123"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_total_cost_by_user(user_id)

        assert result == Decimal("0.0")

    @pytest.mark.asyncio
    async def test_verify_ownership(self, repository, mock_session):
        """Test verifying session ownership."""
        session_id = uuid4()
        user_id = "test-user-123"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = session_id
        mock_session.execute.return_value = mock_result

        result = await repository.verify_ownership(session_id, user_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_ownership_not_owner(self, repository, mock_session):
        """Test verifying ownership when user is not the owner."""
        session_id = uuid4()
        user_id = "test-user-123"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.verify_ownership(session_id, user_id)

        assert result is False


class TestBaseRepositoryOperations:
    """Tests for base repository CRUD operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create repository with mock session."""
        return SessionRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_by_id(self, repository, mock_session):
        """Test getting record by ID."""
        record_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_id(record_id)

        mock_session.execute.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repository, mock_session):
        """Test getting non-existent record."""
        record_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_id(record_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_all(self, repository, mock_session):
        """Test getting all records with pagination."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_all(limit=50, offset=0)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update(self, repository, mock_session):
        """Test updating a record."""
        record_id = uuid4()
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_instance
        mock_session.execute.return_value = mock_result

        result = await repository.update(record_id, status="completed")

        assert result == mock_instance
        assert mock_instance.status == "completed"

    @pytest.mark.asyncio
    async def test_update_not_found(self, repository, mock_session):
        """Test updating non-existent record."""
        record_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.update(record_id, status="completed")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, repository, mock_session):
        """Test deleting a record."""
        record_id = uuid4()
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_instance
        mock_session.execute.return_value = mock_result

        result = await repository.delete(record_id)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_instance)

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repository, mock_session):
        """Test deleting non-existent record."""
        record_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.delete(record_id)

        assert result is False
