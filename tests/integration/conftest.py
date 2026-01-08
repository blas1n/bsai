"""Integration test fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.auth import get_current_user_id
from agent.api.dependencies import get_db
from agent.api.handlers import register_exception_handlers


@pytest.fixture
def db_session() -> AsyncMock:
    """Create mock database session for integration tests.

    Returns:
        Mock AsyncSession
    """
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    # Create mock execute that returns a mock result with scalars()
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    session.execute = AsyncMock(return_value=mock_result)

    session.refresh = AsyncMock()
    return session


@pytest.fixture
def app(db_session: AsyncMock) -> FastAPI:
    """Create test FastAPI app for integration tests."""
    from agent.api.routers.mcp import router as mcp_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(mcp_router, prefix="/api/v1")

    # Override dependencies
    async def override_get_db():
        yield db_session

    async def override_get_user_id():
        return "test-user-123"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_user_id

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client for integration tests."""
    return TestClient(app, raise_server_exceptions=False)
