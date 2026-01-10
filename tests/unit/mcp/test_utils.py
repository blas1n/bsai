"""Tests for MCP utility functions."""

from unittest.mock import AsyncMock, MagicMock, patch

from agent.mcp.utils import load_all_mcp_tools, load_tools_from_mcp_server, load_user_mcp_servers


def _create_mock_server(
    name: str = "test-server",
    transport_type: str = "http",
    **kwargs,
) -> MagicMock:
    """Create a mock MCP server configuration."""
    mock = MagicMock()
    mock.name = name
    mock.transport_type = transport_type
    mock.server_url = kwargs.get("server_url", "https://api.example.com/mcp")
    mock.auth_type = kwargs.get("auth_type")
    mock.auth_credentials = kwargs.get("auth_credentials")
    mock.available_tools = kwargs.get("available_tools")
    return mock


class TestLoadUserMcpServers:
    """Tests for load_user_mcp_servers function."""

    async def test_load_servers_success(self):
        """Test loading MCP servers for user."""
        mock_repo = MagicMock()
        mock_servers = [
            _create_mock_server("server1"),
            _create_mock_server("server2"),
        ]
        mock_repo.get_enabled_for_agent = AsyncMock(return_value=mock_servers)

        result = await load_user_mcp_servers(mock_repo, "user-123", "worker")

        assert len(result) == 2
        mock_repo.get_enabled_for_agent.assert_called_once_with("user-123", "worker")

    async def test_load_servers_empty(self):
        """Test loading when no servers found."""
        mock_repo = MagicMock()
        mock_repo.get_enabled_for_agent = AsyncMock(return_value=[])

        result = await load_user_mcp_servers(mock_repo, "user-123", "worker")

        assert result == []

    async def test_load_servers_qa_agent(self):
        """Test loading servers for QA agent."""
        mock_repo = MagicMock()
        mock_servers = [_create_mock_server("qa-server")]
        mock_repo.get_enabled_for_agent = AsyncMock(return_value=mock_servers)

        result = await load_user_mcp_servers(mock_repo, "user-123", "qa")

        assert len(result) == 1
        mock_repo.get_enabled_for_agent.assert_called_once_with("user-123", "qa")


class TestLoadToolsFromMcpServer:
    """Tests for load_tools_from_mcp_server function."""

    async def test_skip_stdio_server(self):
        """Test that stdio servers are skipped."""
        server = _create_mock_server(transport_type="stdio")

        result = await load_tools_from_mcp_server(server)

        assert result == []

    async def test_skip_server_no_url(self):
        """Test that servers without URL are skipped."""
        server = _create_mock_server(server_url=None)
        server.server_url = None

        result = await load_tools_from_mcp_server(server)

        assert result == []

    async def test_skip_auth_required_no_creds(self):
        """Test that servers requiring auth without credentials are skipped."""
        server = _create_mock_server(auth_type="bearer")

        with patch("agent.mcp.utils.build_mcp_auth_headers", return_value=None):
            result = await load_tools_from_mcp_server(server)

        assert result == []

    async def test_load_sse_tools_success(self):
        """Test loading tools from SSE server."""
        server = _create_mock_server(transport_type="sse")

        mock_tool1 = MagicMock()
        mock_tool1.name = "tool1"
        mock_tool1.description = "Tool 1 description"
        mock_tool1.inputSchema = {"type": "object"}

        mock_tool2 = MagicMock()
        mock_tool2.name = "tool2"
        mock_tool2.description = None
        mock_tool2.inputSchema = None

        mock_session = AsyncMock()
        mock_tools_result = MagicMock()
        mock_tools_result.tools = [mock_tool1, mock_tool2]
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)

        with patch("agent.mcp.utils.build_mcp_auth_headers", return_value=None):
            with patch("agent.mcp.utils.sse_client") as mock_sse:
                mock_sse.return_value.__aenter__ = AsyncMock(
                    return_value=(MagicMock(), MagicMock())
                )
                mock_sse.return_value.__aexit__ = AsyncMock()

                with patch("agent.mcp.utils.ClientSession") as mock_client:
                    mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_client.return_value.__aexit__ = AsyncMock()

                    result = await load_tools_from_mcp_server(server)

        assert len(result) == 2
        assert result[0]["name"] == "tool1"
        assert result[0]["description"] == "Tool 1 description"
        assert result[1]["name"] == "tool2"
        assert result[1]["description"] == ""

    async def test_load_http_tools_success(self):
        """Test loading tools from HTTP server."""
        server = _create_mock_server(transport_type="http")

        mock_tool = MagicMock()
        mock_tool.name = "http_tool"
        mock_tool.description = "HTTP tool"
        mock_tool.inputSchema = {"type": "object"}

        mock_session = AsyncMock()
        mock_tools_result = MagicMock()
        mock_tools_result.tools = [mock_tool]
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)

        with patch("agent.mcp.utils.build_mcp_auth_headers", return_value=None):
            with patch("agent.mcp.utils.streamable_http_client") as mock_http:
                mock_http.return_value.__aenter__ = AsyncMock(
                    return_value=(MagicMock(), MagicMock(), MagicMock())
                )
                mock_http.return_value.__aexit__ = AsyncMock()

                with patch("agent.mcp.utils.ClientSession") as mock_client:
                    mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_client.return_value.__aexit__ = AsyncMock()

                    result = await load_tools_from_mcp_server(server)

        assert len(result) == 1
        assert result[0]["name"] == "http_tool"

    async def test_load_tools_with_filter(self):
        """Test loading tools with available_tools filter."""
        server = _create_mock_server(
            transport_type="sse",
            available_tools=["tool1"],
        )

        mock_tool1 = MagicMock()
        mock_tool1.name = "tool1"
        mock_tool1.description = "Allowed"
        mock_tool1.inputSchema = {}

        mock_tool2 = MagicMock()
        mock_tool2.name = "tool2"
        mock_tool2.description = "Not allowed"
        mock_tool2.inputSchema = {}

        mock_session = AsyncMock()
        mock_tools_result = MagicMock()
        mock_tools_result.tools = [mock_tool1, mock_tool2]
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)

        with patch("agent.mcp.utils.build_mcp_auth_headers", return_value=None):
            with patch("agent.mcp.utils.sse_client") as mock_sse:
                mock_sse.return_value.__aenter__ = AsyncMock(
                    return_value=(MagicMock(), MagicMock())
                )
                mock_sse.return_value.__aexit__ = AsyncMock()

                with patch("agent.mcp.utils.ClientSession") as mock_client:
                    mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_client.return_value.__aexit__ = AsyncMock()

                    result = await load_tools_from_mcp_server(server)

        assert len(result) == 1
        assert result[0]["name"] == "tool1"

    async def test_load_tools_connection_error(self):
        """Test loading tools when connection fails."""
        server = _create_mock_server(transport_type="sse")

        with patch("agent.mcp.utils.build_mcp_auth_headers", return_value=None):
            with patch("agent.mcp.utils.sse_client") as mock_sse:
                mock_sse.return_value.__aenter__ = AsyncMock(
                    side_effect=Exception("Connection failed")
                )
                mock_sse.return_value.__aexit__ = AsyncMock()

                result = await load_tools_from_mcp_server(server)

        assert result == []

    async def test_load_http_tools_with_auth(self):
        """Test loading HTTP tools with authentication."""
        server = _create_mock_server(
            transport_type="http",
            auth_type="bearer",
        )

        mock_tool = MagicMock()
        mock_tool.name = "authed_tool"
        mock_tool.description = "Needs auth"
        mock_tool.inputSchema = {}

        mock_session = AsyncMock()
        mock_tools_result = MagicMock()
        mock_tools_result.tools = [mock_tool]
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)

        with patch(
            "agent.mcp.utils.build_mcp_auth_headers", return_value={"Authorization": "Bearer token"}
        ):
            with patch("agent.mcp.utils.streamable_http_client") as mock_http:
                mock_http.return_value.__aenter__ = AsyncMock(
                    return_value=(MagicMock(), MagicMock(), MagicMock())
                )
                mock_http.return_value.__aexit__ = AsyncMock()

                with patch("agent.mcp.utils.ClientSession") as mock_client:
                    mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_client.return_value.__aexit__ = AsyncMock()

                    result = await load_tools_from_mcp_server(server)

        assert len(result) == 1


class TestLoadAllMcpTools:
    """Tests for load_all_mcp_tools function."""

    async def test_load_all_tools_success(self):
        """Test loading tools from multiple servers."""
        server1 = _create_mock_server("server1", transport_type="sse")
        server2 = _create_mock_server("server2", transport_type="http")

        tools1 = [{"name": "tool1", "description": "desc", "inputSchema": {}}]
        tools2 = [{"name": "tool2", "description": "desc", "inputSchema": {}}]

        with patch("agent.mcp.utils.load_tools_from_mcp_server") as mock_load:
            mock_load.side_effect = [tools1, tools2]

            result = await load_all_mcp_tools([server1, server2])

        assert len(result) == 2
        assert "server1" in result
        assert "server2" in result
        assert result["server1"] == tools1
        assert result["server2"] == tools2

    async def test_load_all_tools_empty_servers(self):
        """Test loading tools with empty server list."""
        result = await load_all_mcp_tools([])

        assert result == {}

    async def test_load_all_tools_partial_failure(self):
        """Test loading tools when some servers fail."""
        server1 = _create_mock_server("server1", transport_type="sse")
        server2 = _create_mock_server("server2", transport_type="http")

        tools1 = [{"name": "tool1", "description": "desc", "inputSchema": {}}]

        with patch("agent.mcp.utils.load_tools_from_mcp_server") as mock_load:
            # First server succeeds, second returns empty
            mock_load.side_effect = [tools1, []]

            result = await load_all_mcp_tools([server1, server2])

        # Only server1 should be in result
        assert len(result) == 1
        assert "server1" in result
        assert "server2" not in result

    async def test_load_all_tools_stdio_servers_skipped(self):
        """Test that stdio servers are skipped."""
        server1 = _create_mock_server("stdio-server", transport_type="stdio")
        server2 = _create_mock_server("http-server", transport_type="http")

        tools2 = [{"name": "tool2", "description": "desc", "inputSchema": {}}]

        with patch("agent.mcp.utils.load_tools_from_mcp_server") as mock_load:
            mock_load.side_effect = [[], tools2]

            result = await load_all_mcp_tools([server1, server2])

        assert len(result) == 1
        assert "http-server" in result
