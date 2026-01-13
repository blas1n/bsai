"""
Pytest configuration and fixtures
"""

import sys
from unittest.mock import MagicMock

# Patch mcp module early to avoid pydantic compatibility issues
# This must happen before any agent modules are imported
if "mcp" not in sys.modules:
    _mock_mcp = MagicMock()
    sys.modules["mcp"] = _mock_mcp
    sys.modules["mcp.client"] = MagicMock()
    sys.modules["mcp.client.session"] = MagicMock()
    sys.modules["mcp.client.sse"] = MagicMock()
    sys.modules["mcp.client.streamable_http"] = MagicMock()
    sys.modules["mcp.types"] = MagicMock()

import asyncio

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock application settings for tests"""
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
