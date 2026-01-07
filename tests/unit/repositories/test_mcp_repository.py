"""Unit tests for MCP repositories."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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


class TestMcpServerRepository:
    """Test MCP server repository operations."""

    @pytest.mark.asyncio
    async def test_create_http_server(self, db_session: AsyncSession, user_id: str):
        """Test creating HTTP MCP server configuration."""
        repo = McpServerRepository(db_session)

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

        assert server.id is not None
        assert server.user_id == user_id
        assert server.name == "test-http-server"
        assert server.transport_type == "http"
        assert server.server_url == "https://api.example.com/mcp"
        assert server.auth_type == "bearer"
        assert server.enabled_for_worker is True
        assert server.enabled_for_qa is False
        assert server.is_active is True

    @pytest.mark.asyncio
    async def test_create_stdio_server(self, db_session: AsyncSession, user_id: str):
        """Test creating stdio MCP server configuration."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id=user_id,
            name="test-stdio-server",
            transport_type="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
            env_vars={"NODE_ENV": "production"},
            require_approval="conditional",
        )

        assert server.id is not None
        assert server.transport_type == "stdio"
        assert server.command == "npx"
        assert server.args == ["-y", "@modelcontextprotocol/server-filesystem"]
        assert server.env_vars == {"NODE_ENV": "production"}

    @pytest.mark.asyncio
    async def test_get_by_user(self, db_session: AsyncSession, user_id: str, other_user_id: str):
        """Test retrieving servers by user ID."""
        repo = McpServerRepository(db_session)

        # Create servers for different users
        await repo.create(
            user_id=user_id,
            name="user1-server1",
            transport_type="http",
            server_url="https://api1.example.com",
        )
        await repo.create(
            user_id=user_id,
            name="user1-server2",
            transport_type="http",
            server_url="https://api2.example.com",
        )
        await repo.create(
            user_id=other_user_id,
            name="user2-server1",
            transport_type="http",
            server_url="https://api3.example.com",
        )

        # Get servers for user1
        servers = await repo.get_by_user(user_id)

        assert len(servers) == 2
        assert all(s.user_id == user_id for s in servers)
        assert {s.name for s in servers} == {"user1-server1", "user1-server2"}

    @pytest.mark.asyncio
    async def test_get_by_user_active_only(self, db_session: AsyncSession, user_id: str):
        """Test retrieving only active servers."""
        repo = McpServerRepository(db_session)

        # Create active and inactive servers
        active = await repo.create(
            user_id=user_id,
            name="active-server",
            transport_type="http",
            server_url="https://active.example.com",
            is_active=True,
        )
        await repo.create(
            user_id=user_id,
            name="inactive-server",
            transport_type="http",
            server_url="https://inactive.example.com",
            is_active=False,
        )

        # Get only active servers
        servers = await repo.get_by_user(user_id, is_active_only=True)

        assert len(servers) == 1
        assert servers[0].id == active.id

        # Get all servers
        all_servers = await repo.get_by_user(user_id, is_active_only=False)

        assert len(all_servers) == 2

    @pytest.mark.asyncio
    async def test_get_by_id_and_user(
        self, db_session: AsyncSession, user_id: str, other_user_id: str
    ):
        """Test retrieving server by ID with user ownership check."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id=user_id,
            name="test-server",
            transport_type="http",
            server_url="https://api.example.com",
        )

        # Should retrieve when user matches
        retrieved = await repo.get_by_id_and_user(server.id, user_id)
        assert retrieved is not None
        assert retrieved.id == server.id

        # Should return None when user doesn't match
        not_found = await repo.get_by_id_and_user(server.id, other_user_id)
        assert not_found is None

    @pytest.mark.asyncio
    async def test_get_enabled_for_agent(self, db_session: AsyncSession, user_id: str):
        """Test retrieving servers enabled for specific agent."""
        repo = McpServerRepository(db_session)

        # Create servers with different agent enablement
        await repo.create(
            user_id=user_id,
            name="worker-only",
            transport_type="http",
            server_url="https://worker.example.com",
            enabled_for_worker=True,
            enabled_for_qa=False,
        )
        await repo.create(
            user_id=user_id,
            name="qa-only",
            transport_type="http",
            server_url="https://qa.example.com",
            enabled_for_worker=False,
            enabled_for_qa=True,
        )
        await repo.create(
            user_id=user_id,
            name="both",
            transport_type="http",
            server_url="https://both.example.com",
            enabled_for_worker=True,
            enabled_for_qa=True,
        )

        # Get servers for worker agent
        worker_servers = await repo.get_enabled_for_agent(user_id, "worker")
        assert len(worker_servers) == 2
        assert {s.name for s in worker_servers} == {"worker-only", "both"}

        # Get servers for QA agent
        qa_servers = await repo.get_enabled_for_agent(user_id, "qa")
        assert len(qa_servers) == 2
        assert {s.name for s in qa_servers} == {"qa-only", "both"}

    @pytest.mark.asyncio
    async def test_update_by_user(self, db_session: AsyncSession, user_id: str, other_user_id: str):
        """Test updating server with user ownership check."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id=user_id,
            name="original-name",
            transport_type="http",
            server_url="https://original.example.com",
            description="Original description",
        )

        # Should update when user matches
        updated = await repo.update_by_user(
            server_id=server.id,
            user_id=user_id,
            name="updated-name",
            description="Updated description",
        )

        assert updated is not None
        assert updated.name == "updated-name"
        assert updated.description == "Updated description"

        # Should return None when user doesn't match
        not_updated = await repo.update_by_user(
            server_id=server.id,
            user_id=other_user_id,
            name="hacker-name",
        )

        assert not_updated is None

        # Verify original user's server was not modified
        retrieved = await repo.get_by_id(server.id)
        assert retrieved.name == "updated-name"  # Still has user1's update

    @pytest.mark.asyncio
    async def test_delete_by_user_soft_delete(
        self, db_session: AsyncSession, user_id: str, other_user_id: str
    ):
        """Test soft deleting server with user ownership check."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id=user_id,
            name="to-delete",
            transport_type="http",
            server_url="https://delete.example.com",
        )

        # Other user cannot delete
        success = await repo.delete_by_user(server.id, other_user_id)
        assert success is False

        # Owner can delete
        success = await repo.delete_by_user(server.id, user_id)
        assert success is True

        # Server should be soft deleted (is_active=False)
        deleted = await repo.get_by_id(server.id)
        assert deleted.is_active is False

        # Should not appear in active-only queries
        active_servers = await repo.get_by_user(user_id, is_active_only=True)
        assert not any(s.id == server.id for s in active_servers)


class TestMcpToolLogRepository:
    """Test MCP tool execution log repository operations."""

    @pytest.mark.asyncio
    async def test_log_execution_success(self, db_session: AsyncSession, user_id: str):
        """Test logging successful tool execution."""
        repo = McpToolLogRepository(db_session)

        session_id = uuid4()
        task_id = uuid4()
        milestone_id = uuid4()
        mcp_server_id = uuid4()

        log = await repo.log_execution(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            mcp_server_id=mcp_server_id,
            tool_name="read_file",
            tool_input={"path": "/data/test.json"},
            tool_output={"content": "file content"},
            agent_type="worker",
            status="success",
            execution_time_ms=123,
            required_approval=False,
            approved_by_user=None,
        )

        assert log.id is not None
        assert log.user_id == user_id
        assert log.session_id == session_id
        assert log.tool_name == "read_file"
        assert log.status == "success"
        assert log.execution_time_ms == 123

    @pytest.mark.asyncio
    async def test_log_execution_error(self, db_session: AsyncSession, user_id: str):
        """Test logging failed tool execution."""
        repo = McpToolLogRepository(db_session)

        log = await repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=uuid4(),
            tool_name="write_file",
            tool_input={"path": "/readonly/file.txt"},
            agent_type="qa",
            status="error",
            error_message="Permission denied",
            required_approval=True,
            approved_by_user=True,
        )

        assert log.status == "error"
        assert log.error_message == "Permission denied"
        assert log.required_approval is True
        assert log.approved_by_user is True

    @pytest.mark.asyncio
    async def test_get_by_session(self, db_session: AsyncSession, user_id: str):
        """Test retrieving logs by session ID."""
        repo = McpToolLogRepository(db_session)

        session1 = uuid4()
        session2 = uuid4()
        mcp_server_id = uuid4()

        # Create logs for different sessions
        await repo.log_execution(
            user_id=user_id,
            session_id=session1,
            mcp_server_id=mcp_server_id,
            tool_name="tool1",
            tool_input={},
            agent_type="worker",
            status="success",
            required_approval=False,
        )
        await repo.log_execution(
            user_id=user_id,
            session_id=session1,
            mcp_server_id=mcp_server_id,
            tool_name="tool2",
            tool_input={},
            agent_type="worker",
            status="success",
            required_approval=False,
        )
        await repo.log_execution(
            user_id=user_id,
            session_id=session2,
            mcp_server_id=mcp_server_id,
            tool_name="tool3",
            tool_input={},
            agent_type="worker",
            status="success",
            required_approval=False,
        )

        # Get logs for session1
        logs = await repo.get_by_session(session1)

        assert len(logs) == 2
        assert all(log.session_id == session1 for log in logs)
        assert {log.tool_name for log in logs} == {"tool1", "tool2"}

    @pytest.mark.asyncio
    async def test_get_by_user_with_filters(
        self, db_session: AsyncSession, user_id: str, other_user_id: str
    ):
        """Test retrieving logs by user with status and agent filters."""
        repo = McpToolLogRepository(db_session)

        mcp_server_id = uuid4()

        # Create logs with different statuses and agents
        await repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=mcp_server_id,
            tool_name="worker-success",
            tool_input={},
            agent_type="worker",
            status="success",
            required_approval=False,
        )
        await repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=mcp_server_id,
            tool_name="worker-error",
            tool_input={},
            agent_type="worker",
            status="error",
            required_approval=False,
        )
        await repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=mcp_server_id,
            tool_name="qa-success",
            tool_input={},
            agent_type="qa",
            status="success",
            required_approval=False,
        )
        await repo.log_execution(
            user_id=other_user_id,
            session_id=uuid4(),
            mcp_server_id=mcp_server_id,
            tool_name="other-user",
            tool_input={},
            agent_type="worker",
            status="success",
            required_approval=False,
        )

        # Filter by user and status
        error_logs = await repo.get_by_user(user_id, status_filter="error")
        assert len(error_logs) == 1
        assert error_logs[0].tool_name == "worker-error"

        # Filter by user and agent type
        worker_logs = await repo.get_by_user(user_id, agent_type_filter="worker")
        assert len(worker_logs) == 2
        assert {log.tool_name for log in worker_logs} == {"worker-success", "worker-error"}

        # Filter by both
        qa_success_logs = await repo.get_by_user(
            user_id,
            status_filter="success",
            agent_type_filter="qa",
        )
        assert len(qa_success_logs) == 1
        assert qa_success_logs[0].tool_name == "qa-success"

    @pytest.mark.asyncio
    async def test_get_by_mcp_server(self, db_session: AsyncSession, user_id: str):
        """Test retrieving logs by MCP server ID."""
        repo = McpToolLogRepository(db_session)

        server1 = uuid4()
        server2 = uuid4()

        # Create logs for different servers
        await repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=server1,
            tool_name="server1-tool1",
            tool_input={},
            agent_type="worker",
            status="success",
            required_approval=False,
        )
        await repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=server1,
            tool_name="server1-tool2",
            tool_input={},
            agent_type="worker",
            status="success",
            required_approval=False,
        )
        await repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=server2,
            tool_name="server2-tool1",
            tool_input={},
            agent_type="worker",
            status="success",
            required_approval=False,
        )

        # Get logs for server1
        logs = await repo.get_by_mcp_server(server1)

        assert len(logs) == 2
        assert all(log.mcp_server_id == server1 for log in logs)

    @pytest.mark.asyncio
    async def test_get_error_count_by_server(self, db_session: AsyncSession, user_id: str):
        """Test counting errors for an MCP server."""
        repo = McpToolLogRepository(db_session)

        server_id = uuid4()

        # Create logs with different statuses
        await repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=server_id,
            tool_name="success-tool",
            tool_input={},
            agent_type="worker",
            status="success",
            required_approval=False,
        )
        await repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=server_id,
            tool_name="error-tool1",
            tool_input={},
            agent_type="worker",
            status="error",
            required_approval=False,
        )
        await repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=server_id,
            tool_name="error-tool2",
            tool_input={},
            agent_type="worker",
            status="error",
            required_approval=False,
        )

        # Count errors
        error_count = await repo.get_error_count_by_server(server_id)

        assert error_count == 2
