"""Unit tests for MCP API endpoints."""

from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import McpSettings
from agent.db.repository.mcp_server_repo import McpServerRepository
from agent.db.repository.mcp_tool_log_repo import McpToolLogRepository
from agent.mcp.security import CredentialEncryption


@pytest.fixture
def mcp_settings() -> McpSettings:
    """Create test MCP settings."""
    return McpSettings(
        encryption_key=CredentialEncryption.generate_key(),
        allowed_stdio_commands=["node", "python3", "npx", "deno"],
    )


@pytest.fixture
def user_id() -> str:
    """Generate test user ID."""
    return "test-user-123"


@pytest.fixture
def auth_headers(user_id: str) -> dict[str, str]:
    """Create authentication headers for test user."""
    return {"X-User-ID": user_id}


class TestListMcpServers:
    """Test GET /api/v1/mcp/servers endpoint."""

    def test_list_mcp_servers_empty(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test listing MCP servers when user has none."""
        response = client.get("/api/v1/mcp/servers", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_list_mcp_servers_multiple(
        self,
        client: TestClient,
        db_session: AsyncSession,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test listing multiple MCP servers."""
        repo = McpServerRepository(db_session)

        # Create test servers
        await repo.create(
            user_id=user_id,
            name="server1",
            transport_type="http",
            server_url="https://api1.example.com",
        )
        await repo.create(
            user_id=user_id,
            name="server2",
            transport_type="stdio",
            command="node",
            args=["server.js"],
        )

        response = client.get("/api/v1/mcp/servers", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        assert {s["name"] for s in data} == {"server1", "server2"}

    @pytest.mark.asyncio
    async def test_list_mcp_servers_filters_inactive(
        self,
        client: TestClient,
        db_session: AsyncSession,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test that inactive servers are not listed by default."""
        repo = McpServerRepository(db_session)

        await repo.create(
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

        response = client.get("/api/v1/mcp/servers", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "active-server"

    def test_list_mcp_servers_requires_auth(self, client: TestClient):
        """Test that listing servers requires authentication."""
        response = client.get("/api/v1/mcp/servers")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetMcpServer:
    """Test GET /api/v1/mcp/servers/{server_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_mcp_server_success(
        self,
        client: TestClient,
        db_session: AsyncSession,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test retrieving MCP server by ID."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id=user_id,
            name="test-server",
            description="Test description",
            transport_type="http",
            server_url="https://api.example.com",
            auth_type="bearer",
        )

        response = client.get(f"/api/v1/mcp/servers/{server.id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(server.id)
        assert data["name"] == "test-server"
        assert data["description"] == "Test description"
        assert data["transport_type"] == "http"
        assert data["server_url"] == "https://api.example.com"

    @pytest.mark.asyncio
    async def test_get_mcp_server_with_stdio_config(
        self,
        client: TestClient,
        db_session: AsyncSession,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test retrieving stdio server includes config."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id=user_id,
            name="stdio-server",
            transport_type="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
            env_vars={"NODE_ENV": "production"},
        )

        response = client.get(f"/api/v1/mcp/servers/{server.id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["stdio_config"] is not None
        assert data["stdio_config"]["command"] == "npx"
        assert data["stdio_config"]["args"] == ["-y", "@modelcontextprotocol/server-filesystem"]
        assert data["stdio_config"]["env_vars"] == {"NODE_ENV": "production"}

    def test_get_mcp_server_not_found(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test retrieving non-existent server returns 404."""
        fake_id = uuid4()
        response = client.get(f"/api/v1/mcp/servers/{fake_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_mcp_server_wrong_user(
        self,
        client: TestClient,
        db_session: AsyncSession,
    ):
        """Test retrieving another user's server returns 404."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id="other-user",
            name="other-server",
            transport_type="http",
            server_url="https://other.example.com",
        )

        # Try to access with different user
        response = client.get(
            f"/api/v1/mcp/servers/{server.id}",
            headers={"X-User-ID": "test-user-123"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestCreateMcpServer:
    """Test POST /api/v1/mcp/servers endpoint."""

    def test_create_http_server(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mcp_settings: McpSettings,
    ):
        """Test creating HTTP MCP server."""
        payload = {
            "name": "test-http-server",
            "description": "Test HTTP server",
            "transport_type": "http",
            "server_url": "https://api.example.com/mcp",
            "auth_type": "bearer",
            "auth_credentials": {"token": "secret-token"},
            "require_approval": "always",
            "enabled_for_worker": True,
            "enabled_for_qa": False,
        }

        response = client.post("/api/v1/mcp/servers", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "test-http-server"
        assert data["transport_type"] == "http"
        assert data["server_url"] == "https://api.example.com/mcp"
        assert data["has_credentials"] is True
        assert data["enabled_for_worker"] is True
        assert data["enabled_for_qa"] is False

    def test_create_stdio_server(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test creating stdio MCP server."""
        payload = {
            "name": "test-stdio-server",
            "transport_type": "stdio",
            "command": "node",
            "args": ["mcp-server.js"],
            "env_vars": {"DEBUG": "true"},
            "require_approval": "conditional",
        }

        response = client.post("/api/v1/mcp/servers", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "test-stdio-server"
        assert data["transport_type"] == "stdio"
        assert data["has_stdio_config"] is True

    def test_create_server_invalid_name(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test creating server with invalid name fails validation."""
        payload = {
            "name": "invalid name with spaces!",
            "transport_type": "http",
            "server_url": "https://api.example.com",
        }

        response = client.post("/api/v1/mcp/servers", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_server_missing_required_field(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test creating server without required fields fails."""
        # HTTP server missing server_url
        payload = {
            "name": "incomplete-server",
            "transport_type": "http",
        }

        response = client.post("/api/v1/mcp/servers", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_server_blocks_disallowed_command(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test creating server with disallowed stdio command fails."""
        payload = {
            "name": "malicious-server",
            "transport_type": "stdio",
            "command": "bash",  # Not in allowlist
            "args": ["-c", "rm -rf /"],
        }

        response = client.post("/api/v1/mcp/servers", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not allowed" in response.json()["detail"].lower()

    def test_create_server_blocks_localhost_url(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test creating server with localhost URL fails SSRF check."""
        payload = {
            "name": "ssrf-server",
            "transport_type": "http",
            "server_url": "http://localhost:8080/admin",
        }

        response = client.post("/api/v1/mcp/servers", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "blocked" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_server_duplicate_name(
        self,
        client: TestClient,
        db_session: AsyncSession,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test creating server with duplicate name fails."""
        repo = McpServerRepository(db_session)

        # Create existing server
        await repo.create(
            user_id=user_id,
            name="existing-server",
            transport_type="http",
            server_url="https://existing.example.com",
        )

        # Try to create duplicate
        payload = {
            "name": "existing-server",
            "transport_type": "http",
            "server_url": "https://new.example.com",
        }

        response = client.post("/api/v1/mcp/servers", json=payload, headers=auth_headers)

        assert response.status_code == status.HTTP_409_CONFLICT


class TestUpdateMcpServer:
    """Test PATCH /api/v1/mcp/servers/{server_id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_server_success(
        self,
        client: TestClient,
        db_session: AsyncSession,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test updating MCP server configuration."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id=user_id,
            name="original-name",
            description="Original description",
            transport_type="http",
            server_url="https://original.example.com",
        )

        payload = {
            "name": "updated-name",
            "description": "Updated description",
        }

        response = client.patch(
            f"/api/v1/mcp/servers/{server.id}",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "updated-name"
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_server_wrong_user(
        self,
        client: TestClient,
        db_session: AsyncSession,
    ):
        """Test updating another user's server fails."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id="other-user",
            name="other-server",
            transport_type="http",
            server_url="https://other.example.com",
        )

        payload = {"name": "hacked-name"}

        response = client.patch(
            f"/api/v1/mcp/servers/{server.id}",
            json=payload,
            headers={"X-User-ID": "test-user-123"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_server_not_found(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test updating non-existent server returns 404."""
        fake_id = uuid4()
        payload = {"name": "new-name"}

        response = client.patch(
            f"/api/v1/mcp/servers/{fake_id}",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteMcpServer:
    """Test DELETE /api/v1/mcp/servers/{server_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_server_success(
        self,
        client: TestClient,
        db_session: AsyncSession,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test deleting MCP server (soft delete)."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id=user_id,
            name="to-delete",
            transport_type="http",
            server_url="https://delete.example.com",
        )

        response = client.delete(f"/api/v1/mcp/servers/{server.id}", headers=auth_headers)

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify soft delete
        deleted = await repo.get_by_id(server.id)
        assert deleted.is_active is False

    @pytest.mark.asyncio
    async def test_delete_server_wrong_user(
        self,
        client: TestClient,
        db_session: AsyncSession,
    ):
        """Test deleting another user's server fails."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id="other-user",
            name="other-server",
            transport_type="http",
            server_url="https://other.example.com",
        )

        response = client.delete(
            f"/api/v1/mcp/servers/{server.id}",
            headers={"X-User-ID": "test-user-123"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_server_not_found(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test deleting non-existent server returns 404."""
        fake_id = uuid4()

        response = client.delete(f"/api/v1/mcp/servers/{fake_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestTestMcpServer:
    """Test POST /api/v1/mcp/servers/{server_id}/test endpoint."""

    @pytest.mark.asyncio
    async def test_test_stdio_server_not_supported(
        self,
        client: TestClient,
        db_session: AsyncSession,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test that testing stdio servers from backend is not supported."""
        repo = McpServerRepository(db_session)

        server = await repo.create(
            user_id=user_id,
            name="stdio-server",
            transport_type="stdio",
            command="node",
            args=["server.js"],
        )

        response = client.post(
            f"/api/v1/mcp/servers/{server.id}/test",
            json={},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "stdio" in response.json()["detail"].lower()

    def test_test_server_not_found(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test testing non-existent server returns 404."""
        fake_id = uuid4()

        response = client.post(
            f"/api/v1/mcp/servers/{fake_id}/test",
            json={},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGetMcpLogs:
    """Test GET /api/v1/mcp/logs endpoint."""

    @pytest.mark.asyncio
    async def test_get_logs_empty(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test getting logs when user has none."""
        response = client.get("/api/v1/mcp/logs", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_get_logs_with_filters(
        self,
        client: TestClient,
        db_session: AsyncSession,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test getting logs with status and agent filters."""
        log_repo = McpToolLogRepository(db_session)
        server_repo = McpServerRepository(db_session)

        # Create test server
        server = await server_repo.create(
            user_id=user_id,
            name="test-server",
            transport_type="http",
            server_url="https://api.example.com",
        )

        # Create test logs
        await log_repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=server.id,
            tool_name="worker-success",
            tool_input={},
            agent_type="worker",
            status="success",
            required_approval=False,
        )
        await log_repo.log_execution(
            user_id=user_id,
            session_id=uuid4(),
            mcp_server_id=server.id,
            tool_name="qa-error",
            tool_input={},
            agent_type="qa",
            status="error",
            error_message="Test error",
            required_approval=False,
        )

        # Filter by status
        response = client.get(
            "/api/v1/mcp/logs",
            params={"status": "error"},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["tool_name"] == "qa-error"

        # Filter by agent type
        response = client.get(
            "/api/v1/mcp/logs",
            params={"agent_type": "worker"},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["tool_name"] == "worker-success"

    def test_get_logs_pagination(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test logs pagination parameters."""
        response = client.get(
            "/api/v1/mcp/logs",
            params={"limit": 50, "offset": 10},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["limit"] == 50
        assert data["offset"] == 10

    def test_get_logs_invalid_parameters(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ):
        """Test logs with invalid parameters."""
        # Invalid limit (too large)
        response = client.get(
            "/api/v1/mcp/logs",
            params={"limit": 2000},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Invalid status
        response = client.get(
            "/api/v1/mcp/logs",
            params={"status": "invalid_status"},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
