"""Integration tests for MCP repositories.

These tests use mocked database session to verify repository logic.
For true integration tests, a real database setup is required.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.repository.mcp_server_repo import McpServerRepository
from agent.db.repository.mcp_tool_log_repo import McpToolLogRepository


@pytest.fixture
def user_id() -> str:
    """Generate test user ID."""
    return "test-user-123"


@pytest.fixture
def other_user_id() -> str:
    """Generate different test user ID."""
    return "other-user-456"


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


class TestMcpServerRepository:
    """Test MCP server repository operations."""

    @pytest.mark.asyncio
    async def test_create_http_server(self, mock_session: AsyncMock, user_id: str):
        """Test creating HTTP MCP server configuration."""
        repo = McpServerRepository(mock_session)
        server_id = uuid4()

        # Mock refresh to set id
        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, "id", server_id))

        server = await repo.create(
            user_id=user_id,
            name="test-http-server",
            description="Test HTTP MCP server",
            transport_type="http",
            server_url="https://api.example.com/mcp",
            auth_type="bearer",
            auth_credentials="encrypted-token",
            require_approval="always",
            enabled_for_worker=True,
            enabled_for_qa=False,
        )

        assert server.user_id == user_id
        assert server.name == "test-http-server"
        assert server.transport_type == "http"
        assert server.server_url == "https://api.example.com/mcp"
        assert server.auth_type == "bearer"
        assert server.enabled_for_worker is True
        assert server.enabled_for_qa is False
        # Note: is_active defaults to True in DB, but mock doesn't set it
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_stdio_server(self, mock_session: AsyncMock, user_id: str):
        """Test creating stdio MCP server configuration."""
        repo = McpServerRepository(mock_session)
        server_id = uuid4()

        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, "id", server_id))

        server = await repo.create(
            user_id=user_id,
            name="test-stdio-server",
            transport_type="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
            env_vars={"NODE_ENV": "production"},
            require_approval="conditional",
        )

        assert server.transport_type == "stdio"
        assert server.command == "npx"
        assert server.args == ["-y", "@modelcontextprotocol/server-filesystem"]
        assert server.env_vars == {"NODE_ENV": "production"}

    @pytest.mark.asyncio
    async def test_get_by_user(self, mock_session: AsyncMock, user_id: str, other_user_id: str):
        """Test retrieving servers by user ID."""
        repo = McpServerRepository(mock_session)

        # Create mock servers
        mock_server1 = MagicMock()
        mock_server1.id = uuid4()
        mock_server1.user_id = user_id
        mock_server1.name = "server1"

        mock_server2 = MagicMock()
        mock_server2.id = uuid4()
        mock_server2.user_id = user_id
        mock_server2.name = "server2"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_server1, mock_server2]
        mock_session.execute = AsyncMock(return_value=mock_result)

        servers = await repo.get_by_user(user_id)

        assert len(servers) == 2
        assert {s.name for s in servers} == {"server1", "server2"}

    @pytest.mark.asyncio
    async def test_get_by_user_active_only(self, mock_session: AsyncMock, user_id: str):
        """Test retrieving only active servers."""
        repo = McpServerRepository(mock_session)

        mock_server = MagicMock()
        mock_server.id = uuid4()
        mock_server.user_id = user_id
        mock_server.name = "active-server"
        mock_server.is_active = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_server]
        mock_session.execute = AsyncMock(return_value=mock_result)

        servers = await repo.get_by_user(user_id, is_active_only=True)

        assert len(servers) == 1
        assert servers[0].name == "active-server"

    @pytest.mark.asyncio
    async def test_get_by_id_and_user(self, mock_session: AsyncMock, user_id: str):
        """Test retrieving server by ID and user."""
        repo = McpServerRepository(mock_session)
        server_id = uuid4()

        mock_server = MagicMock()
        mock_server.id = server_id
        mock_server.user_id = user_id
        mock_server.name = "my-server"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_server
        mock_session.execute = AsyncMock(return_value=mock_result)

        server = await repo.get_by_id_and_user(server_id, user_id)

        assert server is not None
        assert server.name == "my-server"

    @pytest.mark.asyncio
    async def test_get_enabled_for_agent(self, mock_session: AsyncMock, user_id: str):
        """Test retrieving servers enabled for specific agent type."""
        repo = McpServerRepository(mock_session)

        mock_server = MagicMock()
        mock_server.id = uuid4()
        mock_server.user_id = user_id
        mock_server.name = "worker-server"
        mock_server.enabled_for_worker = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_server]
        mock_session.execute = AsyncMock(return_value=mock_result)

        servers = await repo.get_enabled_for_agent(user_id, "worker")

        assert len(servers) == 1
        assert servers[0].name == "worker-server"

    @pytest.mark.asyncio
    async def test_update_by_user(self, mock_session: AsyncMock, user_id: str):
        """Test updating server by user."""
        repo = McpServerRepository(mock_session)
        server_id = uuid4()

        mock_server = MagicMock()
        mock_server.id = server_id
        mock_server.user_id = user_id
        mock_server.name = "old-name"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_server
        mock_session.execute = AsyncMock(return_value=mock_result)

        updated = await repo.update_by_user(server_id, user_id, name="new-name")

        assert updated is not None
        assert updated.name == "new-name"
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_user_soft_delete(self, mock_session: AsyncMock, user_id: str):
        """Test soft deleting server."""
        repo = McpServerRepository(mock_session)
        server_id = uuid4()

        mock_server = MagicMock()
        mock_server.id = server_id
        mock_server.user_id = user_id
        mock_server.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_server
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await repo.delete_by_user(server_id, user_id)

        assert result is True
        assert mock_server.is_active is False
        mock_session.flush.assert_called_once()


class TestMcpToolLogRepository:
    """Test MCP tool log repository operations."""

    @pytest.mark.asyncio
    async def test_log_execution_success(self, mock_session: AsyncMock, user_id: str):
        """Test logging successful tool execution."""
        repo = McpToolLogRepository(mock_session)
        server_id = uuid4()
        session_id = uuid4()
        log_id = uuid4()

        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, "id", log_id))

        log = await repo.log_execution(
            user_id=user_id,
            session_id=session_id,
            mcp_server_id=server_id,
            tool_name="test-tool",
            tool_input={"arg": "value"},
            agent_type="worker",
            status="success",
            tool_output={"result": "ok"},
            required_approval=False,
            execution_time_ms=150,
        )

        assert log.user_id == user_id
        assert log.tool_name == "test-tool"
        assert log.status == "success"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_execution_error(self, mock_session: AsyncMock, user_id: str):
        """Test logging failed tool execution."""
        repo = McpToolLogRepository(mock_session)
        server_id = uuid4()
        session_id = uuid4()
        log_id = uuid4()

        mock_session.refresh = AsyncMock(side_effect=lambda x: setattr(x, "id", log_id))

        log = await repo.log_execution(
            user_id=user_id,
            session_id=session_id,
            mcp_server_id=server_id,
            tool_name="failing-tool",
            tool_input={},
            agent_type="qa",
            status="error",
            error_message="Connection failed",
            required_approval=False,
        )

        assert log.status == "error"
        assert log.error_message == "Connection failed"

    @pytest.mark.asyncio
    async def test_get_by_session(self, mock_session: AsyncMock, user_id: str):
        """Test retrieving logs by session."""
        repo = McpToolLogRepository(mock_session)
        session_id = uuid4()

        mock_log = MagicMock()
        mock_log.id = uuid4()
        mock_log.session_id = session_id
        mock_log.tool_name = "test-tool"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_session.execute = AsyncMock(return_value=mock_result)

        logs = await repo.get_by_session(session_id)

        assert len(logs) == 1
        assert logs[0].tool_name == "test-tool"

    @pytest.mark.asyncio
    async def test_get_by_user_with_filters(self, mock_session: AsyncMock, user_id: str):
        """Test retrieving logs with filters."""
        repo = McpToolLogRepository(mock_session)

        mock_log = MagicMock()
        mock_log.id = uuid4()
        mock_log.user_id = user_id
        mock_log.status = "error"
        mock_log.agent_type = "worker"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_session.execute = AsyncMock(return_value=mock_result)

        logs = await repo.get_by_user(
            user_id,
            limit=10,
            offset=0,
            status_filter="error",
            agent_type_filter="worker",
        )

        assert len(logs) == 1
        assert logs[0].status == "error"

    @pytest.mark.asyncio
    async def test_get_by_mcp_server(self, mock_session: AsyncMock, user_id: str):
        """Test retrieving logs by MCP server."""
        repo = McpToolLogRepository(mock_session)
        server_id = uuid4()

        mock_log = MagicMock()
        mock_log.id = uuid4()
        mock_log.mcp_server_id = server_id
        mock_log.tool_name = "server-tool"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_session.execute = AsyncMock(return_value=mock_result)

        logs = await repo.get_by_mcp_server(server_id)

        assert len(logs) == 1
        assert logs[0].tool_name == "server-tool"

    @pytest.mark.asyncio
    async def test_get_error_count_by_server(self, mock_session: AsyncMock, user_id: str):
        """Test getting error count by server."""
        repo = McpToolLogRepository(mock_session)
        server_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_session.execute = AsyncMock(return_value=mock_result)

        count = await repo.get_error_count_by_server(server_id)

        assert count == 5
