"""Tests for MCP router endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.api.exceptions import NotFoundError, ValidationError
from agent.api.routers.mcp import (
    _build_server_response,
    _build_wellknown_url,
    _discover_oauth_metadata,
    _initiate_oauth_flow,
    _register_oauth_client,
    connect_mcp_server,
    list_mcp_tools_from_server,
    oauth_callback,
)
from agent.api.schemas.mcp import McpOAuthCallbackRequest, McpServerDetailResponse
from agent.mcp.security import (
    McpSecurityValidator,
    McpSettings,
    build_mcp_auth_headers,
)


@pytest.fixture
def mock_user_id() -> str:
    """Generate mock user ID."""
    return "test-user-123"


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


def _create_mock_server(
    user_id: str,
    name: str = "Test Server",
    transport_type: str = "http",
    **kwargs,
) -> MagicMock:
    """Create a mock MCP server."""
    mock = MagicMock()
    mock.id = kwargs.get("id", uuid4())
    mock.user_id = user_id
    mock.name = name
    mock.description = kwargs.get("description", "Test description")
    mock.transport_type = transport_type
    mock.server_url = kwargs.get("server_url", "https://example.com/mcp")
    mock.auth_type = kwargs.get("auth_type", "none")
    mock.auth_credentials = kwargs.get("auth_credentials")
    mock.command = kwargs.get("command")
    mock.args = kwargs.get("args", [])
    mock.env_vars = kwargs.get("env_vars", {})
    mock.available_tools = kwargs.get("available_tools", ["tool1", "tool2"])
    mock.require_approval = kwargs.get("require_approval", "none")  # String type expected
    mock.enabled_for_worker = kwargs.get("enabled_for_worker", True)
    mock.enabled_for_qa = kwargs.get("enabled_for_qa", False)
    mock.is_active = kwargs.get("is_active", True)
    now = datetime.now(UTC)
    mock.created_at = kwargs.get("created_at", now)
    mock.updated_at = kwargs.get("updated_at", now)
    return mock


class TestBuildWellknownUrl:
    """Tests for _build_wellknown_url helper."""

    def test_build_wellknown_url_valid_path(self):
        """Test building well-known URL with valid path."""
        settings = McpSettings()
        validator = McpSecurityValidator(settings)

        result = _build_wellknown_url(
            "https://example.com",
            "/.well-known/oauth-authorization-server",
            validator,
        )

        assert result == "https://example.com/.well-known/oauth-authorization-server"

    def test_build_wellknown_url_strips_path(self):
        """Test that URL path is stripped before appending well-known path."""
        settings = McpSettings()
        validator = McpSecurityValidator(settings)

        result = _build_wellknown_url(
            "https://example.com/some/path?query=param",
            "/.well-known/openid-configuration",
            validator,
        )

        assert result == "https://example.com/.well-known/openid-configuration"

    def test_build_wellknown_url_invalid_path(self):
        """Test that invalid well-known paths are rejected."""
        settings = McpSettings()
        validator = McpSecurityValidator(settings)

        with pytest.raises(ValueError, match="Invalid well-known path"):
            _build_wellknown_url(
                "https://example.com",
                "/.well-known/malicious",
                validator,
            )


class TestBuildServerResponse:
    """Tests for _build_server_response helper."""

    @pytest.mark.asyncio
    async def test_build_server_response_basic(self):
        """Test building basic server response."""
        user_id = "test-user"
        mock_server = _create_mock_server(user_id)

        response = await _build_server_response(mock_server, user_id)

        assert response.name == mock_server.name
        assert response.user_id == user_id
        assert response.transport_type == "http"

    @pytest.mark.asyncio
    async def test_build_server_response_unauthorized(self):
        """Test response raises error for wrong user."""
        mock_server = _create_mock_server("owner-user")

        with pytest.raises(NotFoundError):
            await _build_server_response(mock_server, "different-user")

    @pytest.mark.asyncio
    async def test_build_server_response_with_stdio_config(self):
        """Test building response with stdio config."""
        user_id = "test-user"
        mock_server = _create_mock_server(
            user_id,
            transport_type="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server"],
            env_vars={"KEY": "value"},
        )

        response = await _build_server_response(mock_server, user_id, include_stdio_config=True)

        assert isinstance(response, McpServerDetailResponse)
        assert response.stdio_config is not None
        assert response.stdio_config.command == "npx"
        assert response.stdio_config.args == ["-y", "@modelcontextprotocol/server"]


class TestDiscoverOAuthMetadata:
    """Tests for _discover_oauth_metadata helper."""

    @pytest.mark.asyncio
    async def test_discover_oauth_metadata_protected_resource(self):
        """Test discovering OAuth metadata via protected resource endpoint."""
        with patch("agent.api.routers.mcp.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client

            # First call for protected resource
            protected_resource_response = MagicMock()
            protected_resource_response.status_code = 200
            protected_resource_response.json.return_value = {
                "authorization_servers": ["https://auth.example.com"]
            }

            # Second call for auth server metadata
            auth_server_response = MagicMock()
            auth_server_response.status_code = 200
            auth_server_response.json.return_value = {
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
            }

            mock_client.get = AsyncMock(
                side_effect=[protected_resource_response, auth_server_response]
            )

            result = await _discover_oauth_metadata("https://example.com")

            assert result is not None
            assert "authorization_endpoint" in result

    @pytest.mark.asyncio
    async def test_discover_oauth_metadata_fallback_to_oauth_server(self):
        """Test falling back to OAuth authorization server discovery."""
        with patch("agent.api.routers.mcp.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client

            # First call fails (protected resource)
            protected_fail = MagicMock()
            protected_fail.status_code = 404

            # Second call succeeds (oauth-authorization-server)
            oauth_server_response = MagicMock()
            oauth_server_response.status_code = 200
            oauth_server_response.json.return_value = {
                "authorization_endpoint": "https://example.com/authorize",
            }

            mock_client.get = AsyncMock(side_effect=[protected_fail, oauth_server_response])

            result = await _discover_oauth_metadata("https://example.com")

            assert result is not None
            assert result["authorization_endpoint"] == "https://example.com/authorize"

    @pytest.mark.asyncio
    async def test_discover_oauth_metadata_not_found(self):
        """Test when no OAuth metadata is found."""
        with patch("agent.api.routers.mcp.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client

            # All calls fail
            not_found_response = MagicMock()
            not_found_response.status_code = 404

            mock_client.get = AsyncMock(return_value=not_found_response)

            result = await _discover_oauth_metadata("https://example.com")

            assert result is None


class TestRegisterOAuthClient:
    """Tests for _register_oauth_client helper."""

    @pytest.mark.asyncio
    async def test_register_oauth_client_success(self):
        """Test successful OAuth client registration."""
        with patch("agent.api.routers.mcp.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client

            response = MagicMock()
            response.status_code = 201
            response.json.return_value = {
                "client_id": "new-client-id",
                "client_secret": "new-client-secret",
            }
            mock_client.post = AsyncMock(return_value=response)

            result = await _register_oauth_client(
                "https://example.com/register",
                "https://app.example.com/callback",
            )

            assert result is not None
            assert result["client_id"] == "new-client-id"

    @pytest.mark.asyncio
    async def test_register_oauth_client_failure(self):
        """Test OAuth client registration failure."""
        with patch("agent.api.routers.mcp.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client

            response = MagicMock()
            response.status_code = 400
            mock_client.post = AsyncMock(return_value=response)

            result = await _register_oauth_client(
                "https://example.com/register",
                "https://app.example.com/callback",
            )

            assert result is None


class TestInitiateOAuthFlow:
    """Tests for _initiate_oauth_flow helper."""

    @pytest.mark.asyncio
    async def test_initiate_oauth_flow_success(self):
        """Test successful OAuth flow initiation."""
        metadata = {
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
            "client_id": "test-client-id",
        }

        with patch(
            "agent.api.routers.mcp._discover_oauth_metadata", new_callable=AsyncMock
        ) as mock_discover:
            mock_discover.return_value = metadata

            with patch("agent.api.routers.mcp.get_redis") as mock_get_redis:
                mock_redis = MagicMock()
                mock_redis.client = AsyncMock()
                mock_redis.client.setex = AsyncMock()
                mock_get_redis.return_value = mock_redis

                result = await _initiate_oauth_flow(
                    server_url="https://example.com",
                    callback_url="https://app.example.com/callback",
                    user_id="test-user",
                )

                assert result.authorization_url is not None
                assert result.state is not None
                assert "authorize" in result.authorization_url

    @pytest.mark.asyncio
    async def test_initiate_oauth_flow_no_metadata(self):
        """Test OAuth flow when metadata discovery fails."""
        with patch(
            "agent.api.routers.mcp._discover_oauth_metadata", new_callable=AsyncMock
        ) as mock_discover:
            mock_discover.return_value = None

            with pytest.raises(ValidationError, match="Could not discover OAuth configuration"):
                await _initiate_oauth_flow(
                    server_url="https://example.com",
                    callback_url="https://app.example.com/callback",
                    user_id="test-user",
                )

    @pytest.mark.asyncio
    async def test_initiate_oauth_flow_missing_auth_endpoint(self):
        """Test OAuth flow when authorization endpoint is missing."""
        with patch(
            "agent.api.routers.mcp._discover_oauth_metadata", new_callable=AsyncMock
        ) as mock_discover:
            mock_discover.return_value = {"token_endpoint": "https://example.com/token"}

            with pytest.raises(ValidationError, match="missing authorization_endpoint"):
                await _initiate_oauth_flow(
                    server_url="https://example.com",
                    callback_url="https://app.example.com/callback",
                    user_id="test-user",
                )


class TestConnectMcpServer:
    """Tests for connect_mcp_server helper."""

    @pytest.mark.asyncio
    async def test_connect_mcp_server_no_url(self):
        """Test connection fails without URL."""
        mock_server = _create_mock_server("test-user")
        mock_server.server_url = None

        with pytest.raises(ValueError, match="Server URL is not configured"):
            async with connect_mcp_server(mock_server):
                pass

    @pytest.mark.asyncio
    async def test_connect_mcp_server_sse(self):
        """Test SSE transport connection."""
        mock_server = _create_mock_server("test-user", transport_type="sse")

        with patch("agent.api.routers.mcp.sse_client") as mock_sse_client:
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_sse_client.return_value.__aenter__.return_value = (mock_read, mock_write)

            with patch("agent.api.routers.mcp.ClientSession") as MockSession:
                mock_session = AsyncMock()
                mock_session.initialize = AsyncMock()
                MockSession.return_value.__aenter__.return_value = mock_session

                async with connect_mcp_server(mock_server, {"Authorization": "Bearer token"}):
                    pass

                mock_sse_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_mcp_server_http(self):
        """Test HTTP transport connection."""
        mock_server = _create_mock_server("test-user", transport_type="http")

        with patch("agent.api.routers.mcp.streamable_http_client") as mock_http_client:
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_http_client.return_value.__aenter__.return_value = (mock_read, mock_write, None)

            with patch("agent.api.routers.mcp.ClientSession") as MockSession:
                mock_session = AsyncMock()
                mock_session.initialize = AsyncMock()
                MockSession.return_value.__aenter__.return_value = mock_session

                async with connect_mcp_server(mock_server):
                    pass

                mock_http_client.assert_called_once()


class TestListMcpToolsFromServer:
    """Tests for list_mcp_tools_from_server helper."""

    @pytest.mark.asyncio
    async def test_list_mcp_tools_success(self):
        """Test listing tools from server."""
        mock_server = _create_mock_server("test-user")

        with patch("agent.api.routers.mcp.connect_mcp_server") as mock_connect:
            mock_session = AsyncMock()
            mock_tool = MagicMock()
            mock_tool.name = "test_tool"
            mock_tool.description = "A test tool"
            mock_tool.inputSchema = {"type": "object"}

            mock_tools_result = MagicMock()
            mock_tools_result.tools = [mock_tool]
            mock_session.list_tools = AsyncMock(return_value=mock_tools_result)

            mock_connect.return_value.__aenter__.return_value = mock_session

            result = await list_mcp_tools_from_server(mock_server)

            assert len(result) == 1
            assert result[0]["name"] == "test_tool"
            assert result[0]["description"] == "A test tool"


class TestOAuthCallback:
    """Tests for oauth_callback endpoint logic."""

    @pytest.fixture
    def valid_mcp_settings(self):
        """Create valid MCP settings with a real Fernet key."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        return McpSettings(encryption_key=key)

    @pytest.mark.asyncio
    async def test_oauth_callback_invalid_state(self, valid_mcp_settings):
        """Test callback with invalid state."""
        request = McpOAuthCallbackRequest(
            code="auth-code",
            state="invalid-state",
            server_id=uuid4(),
        )

        with (
            patch("agent.api.routers.mcp.get_redis") as mock_get_redis,
            patch("agent.api.routers.mcp.get_mcp_settings", return_value=valid_mcp_settings),
        ):
            mock_redis = MagicMock()
            mock_redis.client = AsyncMock()
            mock_redis.client.get = AsyncMock(return_value=None)
            mock_get_redis.return_value = mock_redis

            mock_db = AsyncMock()

            result = await oauth_callback(request, mock_db, "test-user")

            assert result.success is False
            assert result.error is not None
            assert "Invalid or expired OAuth state" in result.error

    @pytest.mark.asyncio
    async def test_oauth_callback_user_mismatch(self, valid_mcp_settings):
        """Test callback with user mismatch."""
        request = McpOAuthCallbackRequest(
            code="auth-code",
            state="valid-state",
            server_id=uuid4(),
        )

        oauth_data = json.dumps(
            {
                "user_id": "different-user",
                "server_url": "https://example.com",
                "metadata": {"token_endpoint": "https://example.com/token"},
            }
        )

        with (
            patch("agent.api.routers.mcp.get_redis") as mock_get_redis,
            patch("agent.api.routers.mcp.get_mcp_settings", return_value=valid_mcp_settings),
        ):
            mock_redis = MagicMock()
            mock_redis.client = AsyncMock()
            mock_redis.client.get = AsyncMock(return_value=oauth_data)
            mock_redis.client.delete = AsyncMock()
            mock_get_redis.return_value = mock_redis

            mock_db = AsyncMock()

            result = await oauth_callback(request, mock_db, "test-user")

            assert result.success is False
            assert result.error is not None
            assert "does not match current user" in result.error

    @pytest.mark.asyncio
    async def test_oauth_callback_corrupted_state(self, valid_mcp_settings):
        """Test callback with corrupted state data."""
        request = McpOAuthCallbackRequest(
            code="auth-code",
            state="valid-state",
            server_id=uuid4(),
        )

        with (
            patch("agent.api.routers.mcp.get_redis") as mock_get_redis,
            patch("agent.api.routers.mcp.get_mcp_settings", return_value=valid_mcp_settings),
        ):
            mock_redis = MagicMock()
            mock_redis.client = AsyncMock()
            mock_redis.client.get = AsyncMock(return_value="not-valid-json{")
            mock_get_redis.return_value = mock_redis

            mock_db = AsyncMock()

            result = await oauth_callback(request, mock_db, "test-user")

            assert result.success is False
            assert result.error is not None
            assert "Corrupted OAuth state" in result.error

    @pytest.mark.asyncio
    async def test_oauth_callback_missing_token_endpoint(self, valid_mcp_settings):
        """Test callback when token endpoint is missing."""
        request = McpOAuthCallbackRequest(
            code="auth-code",
            state="valid-state",
            server_id=uuid4(),
        )

        oauth_data = json.dumps(
            {
                "user_id": "test-user",
                "server_url": "https://example.com",
                "metadata": {},  # Missing token_endpoint
            }
        )

        with (
            patch("agent.api.routers.mcp.get_redis") as mock_get_redis,
            patch("agent.api.routers.mcp.get_mcp_settings", return_value=valid_mcp_settings),
        ):
            mock_redis = MagicMock()
            mock_redis.client = AsyncMock()
            mock_redis.client.get = AsyncMock(return_value=oauth_data)
            mock_redis.client.delete = AsyncMock()
            mock_get_redis.return_value = mock_redis

            mock_db = AsyncMock()

            result = await oauth_callback(request, mock_db, "test-user")

            assert result.success is False
            assert result.error is not None
            assert "missing token_endpoint" in result.error

    @pytest.mark.asyncio
    async def test_oauth_callback_missing_client_id(self, valid_mcp_settings):
        """Test callback when client_id is missing."""
        request = McpOAuthCallbackRequest(
            code="auth-code",
            state="valid-state",
            server_id=uuid4(),
        )

        oauth_data = json.dumps(
            {
                "user_id": "test-user",
                "server_url": "https://example.com",
                "metadata": {"token_endpoint": "https://example.com/token"},
                # Missing client_id
            }
        )

        with (
            patch("agent.api.routers.mcp.get_redis") as mock_get_redis,
            patch("agent.api.routers.mcp.get_mcp_settings", return_value=valid_mcp_settings),
        ):
            mock_redis = MagicMock()
            mock_redis.client = AsyncMock()
            mock_redis.client.get = AsyncMock(return_value=oauth_data)
            mock_redis.client.delete = AsyncMock()
            mock_get_redis.return_value = mock_redis

            mock_db = AsyncMock()

            result = await oauth_callback(request, mock_db, "test-user")

            assert result.success is False
            assert result.error is not None
            assert "Missing client_id" in result.error


class TestDiscoverOAuthMetadataEdgeCases:
    """Additional tests for _discover_oauth_metadata edge cases."""

    @pytest.mark.asyncio
    async def test_discover_oauth_metadata_openid_fallback(self):
        """Test falling back to OpenID Connect discovery."""
        with patch("agent.api.routers.mcp.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client

            # Protected resource fails
            protected_fail = MagicMock()
            protected_fail.status_code = 404

            # OAuth server fails
            oauth_fail = MagicMock()
            oauth_fail.status_code = 404

            # OpenID Connect succeeds
            openid_response = MagicMock()
            openid_response.status_code = 200
            openid_response.json.return_value = {
                "authorization_endpoint": "https://example.com/openid/authorize",
                "token_endpoint": "https://example.com/openid/token",
            }

            mock_client.get = AsyncMock(side_effect=[protected_fail, oauth_fail, openid_response])

            result = await _discover_oauth_metadata("https://example.com")

            assert result is not None
            assert result["authorization_endpoint"] == "https://example.com/openid/authorize"

    @pytest.mark.asyncio
    async def test_discover_oauth_metadata_exception_handling(self):
        """Test exception handling during discovery."""
        with patch("agent.api.routers.mcp.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client

            # All calls raise exceptions
            mock_client.get = AsyncMock(side_effect=Exception("Network error"))

            result = await _discover_oauth_metadata("https://example.com")

            assert result is None


class TestInitiateOAuthFlowEdgeCases:
    """Additional tests for _initiate_oauth_flow edge cases."""

    @pytest.mark.asyncio
    async def test_initiate_oauth_flow_discovery_exception(self):
        """Test OAuth flow when discovery raises exception."""
        with patch(
            "agent.api.routers.mcp._discover_oauth_metadata", new_callable=AsyncMock
        ) as mock_discover:
            mock_discover.side_effect = Exception("Network error")

            with pytest.raises(ValidationError, match="Failed to discover OAuth"):
                await _initiate_oauth_flow(
                    server_url="https://example.com",
                    callback_url="https://app.example.com/callback",
                    user_id="test-user",
                )

    @pytest.mark.asyncio
    async def test_initiate_oauth_flow_with_registration(self):
        """Test OAuth flow with dynamic client registration."""
        metadata = {
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
            "registration_endpoint": "https://auth.example.com/register",
            # No client_id - needs dynamic registration
        }

        with (
            patch(
                "agent.api.routers.mcp._discover_oauth_metadata", new_callable=AsyncMock
            ) as mock_discover,
            patch(
                "agent.api.routers.mcp._register_oauth_client", new_callable=AsyncMock
            ) as mock_register,
            patch("agent.api.routers.mcp.get_redis") as mock_get_redis,
        ):
            mock_discover.return_value = metadata
            mock_register.return_value = {
                "client_id": "registered-client-id",
                "client_secret": "registered-secret",
            }

            mock_redis = MagicMock()
            mock_redis.client = AsyncMock()
            mock_redis.client.setex = AsyncMock()
            mock_get_redis.return_value = mock_redis

            result = await _initiate_oauth_flow(
                server_url="https://example.com",
                callback_url="https://app.example.com/callback",
                user_id="test-user",
            )

            assert result.authorization_url is not None
            assert result.state is not None
            mock_register.assert_called_once()


class TestBuildMcpAuthHeaders:
    """Tests for build_mcp_auth_headers helper."""

    def test_build_auth_headers_no_auth(self):
        """Test building headers with no auth type returns None."""
        mock_server = _create_mock_server("test-user", auth_type="none")

        result = build_mcp_auth_headers(mock_server)

        assert result is None

    def test_build_auth_headers_no_credentials(self):
        """Test building headers with no credentials returns None."""
        mock_server = _create_mock_server("test-user", auth_type="bearer")
        mock_server.auth_credentials = None

        result = build_mcp_auth_headers(mock_server)

        assert result is None

    def test_build_auth_headers_bearer_token(self):
        """Test building headers with bearer token auth."""
        settings = McpSettings()

        # Create mock with encrypted credentials
        mock_server = _create_mock_server(
            "test-user",
            auth_type="bearer",
        )

        # Mock encrypted credentials that decrypt to a bearer token
        with patch("agent.mcp.security.CredentialEncryption") as MockEncryption:
            mock_encryptor = MagicMock()
            mock_encryptor.decrypt.return_value = {"token": "test-bearer-token"}
            MockEncryption.return_value = mock_encryptor

            mock_server.auth_credentials = "encrypted-data"

            result = build_mcp_auth_headers(mock_server, settings)

            assert result is not None
            assert result.get("Authorization") == "Bearer test-bearer-token"

    def test_build_auth_headers_api_key(self):
        """Test building headers with API key auth."""
        settings = McpSettings()

        mock_server = _create_mock_server(
            "test-user",
            auth_type="api_key",
        )

        with patch("agent.mcp.security.CredentialEncryption") as MockEncryption:
            mock_encryptor = MagicMock()
            mock_encryptor.decrypt.return_value = {
                "api_key": "test-api-key",
                "header_name": "X-API-Key",
            }
            MockEncryption.return_value = mock_encryptor

            mock_server.auth_credentials = "encrypted-data"

            result = build_mcp_auth_headers(mock_server, settings)

            assert result is not None
            assert result.get("X-API-Key") == "test-api-key"

    def test_build_auth_headers_decrypt_failure(self):
        """Test building headers returns None when decryption fails."""
        settings = McpSettings()

        mock_server = _create_mock_server(
            "test-user",
            auth_type="bearer",
        )
        mock_server.auth_credentials = "encrypted-data"

        with patch("agent.mcp.security.CredentialEncryption") as MockEncryption:
            mock_encryptor = MagicMock()
            mock_encryptor.decrypt.side_effect = Exception("Decryption failed")
            MockEncryption.return_value = mock_encryptor

            result = build_mcp_auth_headers(mock_server, settings)

            assert result is None


class TestConnectMcpServerEdgeCases:
    """Additional tests for connect_mcp_server edge cases."""

    @pytest.mark.asyncio
    async def test_connect_mcp_server_defaults_to_http(self):
        """Test connection with unknown transport type defaults to HTTP."""
        mock_server = _create_mock_server("test-user", transport_type="unknown")

        with patch("agent.api.routers.mcp.streamable_http_client") as mock_http_client:
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_http_client.return_value.__aenter__.return_value = (mock_read, mock_write, None)

            with patch("agent.api.routers.mcp.ClientSession") as MockSession:
                mock_session = AsyncMock()
                mock_session.initialize = AsyncMock()
                MockSession.return_value.__aenter__.return_value = mock_session

                async with connect_mcp_server(mock_server):
                    pass

                # Unknown transport defaults to HTTP
                mock_http_client.assert_called_once()
