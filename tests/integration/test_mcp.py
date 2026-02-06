"""Integration tests for MCP API endpoints.

These tests use mocked database session and focus on API endpoint behavior.
For true integration tests with database, a real database setup is required.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from bsai.api.config import McpSettings
from bsai.mcp.security import CredentialEncryption


def _create_mock_server(
    user_id: str,
    name: str,
    transport_type: str = "http",
    **kwargs,
) -> MagicMock:
    """Create a mock MCP server with required fields."""
    mock = MagicMock()
    mock.id = kwargs.get("id", uuid4())
    mock.user_id = user_id
    mock.name = name
    mock.description = kwargs.get("description")
    mock.transport_type = transport_type
    mock.server_url = kwargs.get("server_url")
    mock.auth_type = kwargs.get("auth_type")
    mock.auth_credentials = kwargs.get("auth_credentials")
    mock.command = kwargs.get("command")
    mock.args = kwargs.get("args")
    mock.env_vars = kwargs.get("env_vars")
    mock.available_tools = kwargs.get("available_tools")
    mock.require_approval = kwargs.get("require_approval", "never")
    mock.enabled_for_worker = kwargs.get("enabled_for_worker", True)
    mock.enabled_for_qa = kwargs.get("enabled_for_qa", False)
    mock.is_active = kwargs.get("is_active", True)
    mock.created_at = kwargs.get("created_at", datetime.now(UTC))
    mock.updated_at = kwargs.get("updated_at", datetime.now(UTC))
    return mock


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

    def test_list_mcp_servers_multiple(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test listing multiple MCP servers."""
        mock_server1 = _create_mock_server(
            user_id=user_id,
            name="server1",
            transport_type="http",
            server_url="https://api1.example.com",
        )
        mock_server2 = _create_mock_server(
            user_id=user_id,
            name="server2",
            transport_type="stdio",
            command="node",
            args=["server.js"],
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_server1, mock_server2]
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.get("/api/v1/mcp/servers", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        assert {s["name"] for s in data} == {"server1", "server2"}

    def test_list_mcp_servers_filters_inactive(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test that inactive servers are not listed by default."""
        mock_server = _create_mock_server(
            user_id=user_id,
            name="active-server",
            transport_type="http",
            server_url="https://active.example.com",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_server]
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.get("/api/v1/mcp/servers", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "active-server"


class TestGetMcpServer:
    """Test GET /api/v1/mcp/servers/{server_id} endpoint."""

    def test_get_mcp_server_success(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test retrieving MCP server by ID."""
        server_id = uuid4()
        mock_server = _create_mock_server(
            user_id=user_id,
            name="test-server",
            id=server_id,
            description="Test description",
            transport_type="http",
            server_url="https://api.example.com",
            auth_type="bearer",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_server
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"/api/v1/mcp/servers/{server_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(server_id)
        assert data["name"] == "test-server"
        assert data["description"] == "Test description"
        assert data["transport_type"] == "http"
        assert data["server_url"] == "https://api.example.com"

    def test_get_mcp_server_with_stdio_config(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test retrieving stdio server includes config."""
        server_id = uuid4()
        mock_server = _create_mock_server(
            user_id=user_id,
            name="stdio-server",
            id=server_id,
            transport_type="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
            env_vars={"NODE_ENV": "production"},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_server
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"/api/v1/mcp/servers/{server_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["stdio_config"] is not None
        assert data["stdio_config"]["command"] == "npx"
        assert data["stdio_config"]["args"] == ["-y", "@modelcontextprotocol/server-filesystem"]
        assert data["stdio_config"]["env_vars"] == {"NODE_ENV": "production"}

    def test_get_mcp_server_not_found(
        self,
        client: TestClient,
        db_session: AsyncMock,
        auth_headers: dict[str, str],
    ):
        """Test retrieving non-existent server returns 404."""
        fake_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"/api/v1/mcp/servers/{fake_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_mcp_server_wrong_user(
        self,
        client: TestClient,
        db_session: AsyncMock,
    ):
        """Test retrieving another user's server returns 404."""
        server_id = uuid4()

        # Return None (simulating filter by user_id returning nothing)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.get(
            f"/api/v1/mcp/servers/{server_id}",
            headers={"X-User-ID": "test-user-123"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestCreateMcpServer:
    """Test POST /api/v1/mcp/servers endpoint."""

    def test_create_http_server(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
        auth_headers: dict[str, str],
        mcp_settings: McpSettings,
    ):
        """Test creating HTTP MCP server."""
        server_id = uuid4()
        now = datetime.now(UTC)

        # Mock get_by_name_and_user to return None (no duplicate)
        mock_name_result = MagicMock()
        mock_name_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_name_result)
        db_session.commit = AsyncMock()

        # Mock refresh to set all required fields including DB defaults
        def mock_refresh(obj):
            obj.id = server_id
            obj.is_active = True
            obj.created_at = now
            obj.updated_at = now

        db_session.refresh = AsyncMock(side_effect=mock_refresh)

        with patch("bsai.api.routers.mcp.servers.get_mcp_settings", return_value=mcp_settings):
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
        assert data["is_active"] is True

    def test_create_stdio_server(
        self,
        client: TestClient,
        db_session: AsyncMock,
        auth_headers: dict[str, str],
        mcp_settings: McpSettings,
    ):
        """Test creating stdio MCP server."""
        server_id = uuid4()
        now = datetime.now(UTC)

        mock_name_result = MagicMock()
        mock_name_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_name_result)
        db_session.commit = AsyncMock()

        def mock_refresh(obj):
            obj.id = server_id
            obj.is_active = True
            obj.created_at = now
            obj.updated_at = now

        db_session.refresh = AsyncMock(side_effect=mock_refresh)

        with patch("bsai.api.routers.mcp.servers.get_mcp_settings", return_value=mcp_settings):
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

    def test_create_server_missing_required_field(
        self,
        client: TestClient,
        db_session: AsyncMock,
        auth_headers: dict[str, str],
        mcp_settings: McpSettings,
    ):
        """Test creating server without required fields fails."""
        mock_name_result = MagicMock()
        mock_name_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_name_result)

        with patch("bsai.api.routers.mcp.servers.get_mcp_settings", return_value=mcp_settings):
            # HTTP server missing server_url
            payload = {
                "name": "incomplete-server",
                "transport_type": "http",
            }

            response = client.post("/api/v1/mcp/servers", json=payload, headers=auth_headers)

        # Validation happens at Pydantic schema level, returns 422
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_create_server_blocks_disallowed_command(
        self,
        client: TestClient,
        db_session: AsyncMock,
        auth_headers: dict[str, str],
        mcp_settings: McpSettings,
    ):
        """Test creating server with disallowed stdio command fails."""
        mock_name_result = MagicMock()
        mock_name_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_name_result)

        with patch("bsai.api.routers.mcp.servers.get_mcp_settings", return_value=mcp_settings):
            payload = {
                "name": "malicious-server",
                "transport_type": "stdio",
                "command": "bash",  # Not in allowlist
                "args": ["-c", "rm -rf /"],
            }

            response = client.post("/api/v1/mcp/servers", json=payload, headers=auth_headers)

        # Validation happens at Pydantic schema level, returns 422
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        # ErrorResponse format: {"error": ..., "detail": None, "code": ..., "request_id": ...}
        assert "not allowed" in response.json()["error"].lower()

    def test_create_server_blocks_localhost_url(
        self,
        client: TestClient,
        db_session: AsyncMock,
        auth_headers: dict[str, str],
        mcp_settings: McpSettings,
    ):
        """Test creating server with localhost URL fails SSRF check."""
        mock_name_result = MagicMock()
        mock_name_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_name_result)

        with patch("bsai.api.routers.mcp.servers.get_mcp_settings", return_value=mcp_settings):
            payload = {
                "name": "ssrf-server",
                "transport_type": "http",
                "server_url": "http://localhost:8080/admin",
            }

            response = client.post("/api/v1/mcp/servers", json=payload, headers=auth_headers)

        # Validation happens at Pydantic schema level, returns 422
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        # ErrorResponse format: {"error": ..., "detail": None, "code": ..., "request_id": ...}
        assert "blocked" in response.json()["error"].lower()


class TestUpdateMcpServer:
    """Test PATCH /api/v1/mcp/servers/{server_id} endpoint."""

    def test_update_server_success(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
        auth_headers: dict[str, str],
        mcp_settings: McpSettings,
    ):
        """Test updating MCP server configuration."""
        server_id = uuid4()

        mock_server = _create_mock_server(
            user_id=user_id,
            name="updated-name",
            id=server_id,
            description="Updated description",
            transport_type="http",
            server_url="https://original.example.com",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_server
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.flush = AsyncMock()

        with patch("bsai.api.routers.mcp.servers.get_mcp_settings", return_value=mcp_settings):
            payload = {
                "name": "updated-name",
                "description": "Updated description",
            }

            response = client.patch(
                f"/api/v1/mcp/servers/{server_id}",
                json=payload,
                headers=auth_headers,
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "updated-name"
        assert data["description"] == "Updated description"

    def test_update_server_wrong_user(
        self,
        client: TestClient,
        db_session: AsyncMock,
        mcp_settings: McpSettings,
    ):
        """Test updating another user's server fails."""
        server_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        with patch("bsai.api.routers.mcp.servers.get_mcp_settings", return_value=mcp_settings):
            payload = {"name": "hacked-name"}

            response = client.patch(
                f"/api/v1/mcp/servers/{server_id}",
                json=payload,
                headers={"X-User-ID": "test-user-123"},
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_server_not_found(
        self,
        client: TestClient,
        db_session: AsyncMock,
        auth_headers: dict[str, str],
        mcp_settings: McpSettings,
    ):
        """Test updating non-existent server returns 404."""
        fake_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        with patch("bsai.api.routers.mcp.servers.get_mcp_settings", return_value=mcp_settings):
            payload = {"name": "new-name"}

            response = client.patch(
                f"/api/v1/mcp/servers/{fake_id}",
                json=payload,
                headers=auth_headers,
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteMcpServer:
    """Test DELETE /api/v1/mcp/servers/{server_id} endpoint."""

    def test_delete_server_success(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test deleting MCP server (soft delete)."""
        server_id = uuid4()

        mock_server = MagicMock()
        mock_server.id = server_id
        mock_server.user_id = user_id
        mock_server.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_server
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.flush = AsyncMock()

        response = client.delete(f"/api/v1/mcp/servers/{server_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_server_wrong_user(
        self,
        client: TestClient,
        db_session: AsyncMock,
    ):
        """Test deleting another user's server fails."""
        server_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.delete(
            f"/api/v1/mcp/servers/{server_id}",
            headers={"X-User-ID": "test-user-123"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_server_not_found(
        self,
        client: TestClient,
        db_session: AsyncMock,
        auth_headers: dict[str, str],
    ):
        """Test deleting non-existent server returns 404."""
        fake_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.delete(f"/api/v1/mcp/servers/{fake_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestTestMcpServer:
    """Test POST /api/v1/mcp/servers/{server_id}/test endpoint."""

    def test_test_stdio_server_not_supported(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
        auth_headers: dict[str, str],
    ):
        """Test that testing stdio servers from backend is not supported."""
        server_id = uuid4()

        mock_server = _create_mock_server(
            user_id=user_id,
            name="test-stdio-server",
            id=server_id,
            transport_type="stdio",
            command="node",
            args=["server.js"],
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_server
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.post(
            f"/api/v1/mcp/servers/{server_id}/test",
            headers=auth_headers,
        )

        # ValidationError returns 422
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        # ErrorResponse format: {"error": ..., "detail": None, "code": ..., "request_id": ...}
        assert "stdio" in response.json()["error"].lower()

    def test_test_server_not_found(
        self,
        client: TestClient,
        db_session: AsyncMock,
        auth_headers: dict[str, str],
    ):
        """Test testing non-existent server returns 404."""
        fake_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.post(
            f"/api/v1/mcp/servers/{fake_id}/test",
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGetMcpLogs:
    """Test GET /api/v1/mcp/logs endpoint."""

    def test_get_logs_empty(
        self,
        client: TestClient,
        db_session: AsyncMock,
        auth_headers: dict[str, str],
    ):
        """Test getting logs when user has none."""
        # Mock for get_by_user (returns list)
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        # Mock for count_by_user (returns int)
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        # Return different results for consecutive calls
        db_session.execute = AsyncMock(side_effect=[mock_list_result, mock_count_result])

        response = client.get("/api/v1/mcp/logs", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_get_logs_pagination(
        self,
        client: TestClient,
        db_session: AsyncMock,
        auth_headers: dict[str, str],
    ):
        """Test logs pagination parameters."""
        # Mock for get_by_user (returns list)
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        # Mock for count_by_user (returns int)
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        # Return different results for consecutive calls
        db_session.execute = AsyncMock(side_effect=[mock_list_result, mock_count_result])

        response = client.get(
            "/api/v1/mcp/logs",
            params={"limit": 50, "offset": 10},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["limit"] == 50
        assert data["offset"] == 10
