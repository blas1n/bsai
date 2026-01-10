"""Tests for MCP tool executor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.mcp.executor import McpToolCall, McpToolExecutor, McpToolResult


def _create_mock_server(
    name: str = "test-server",
    transport_type: str = "http",
    require_approval: str = "never",
    **kwargs,
) -> MagicMock:
    """Create a mock MCP server configuration."""
    mock = MagicMock()
    mock.id = kwargs.get("id", uuid4())
    mock.name = name
    mock.transport_type = transport_type
    mock.server_url = kwargs.get("server_url", "https://api.example.com/mcp")
    mock.require_approval = require_approval
    mock.command = kwargs.get("command")
    mock.args = kwargs.get("args", [])
    mock.env_vars = kwargs.get("env_vars", {})
    mock.auth_type = kwargs.get("auth_type")
    mock.auth_credentials = kwargs.get("auth_credentials")
    return mock


@pytest.fixture
def user_id() -> str:
    """Test user ID."""
    return "test-user-123"


@pytest.fixture
def session_id():
    """Test session ID."""
    return uuid4()


@pytest.fixture
def mock_ws_manager() -> MagicMock:
    """Create mock WebSocket manager."""
    manager = MagicMock()
    manager.broadcast_to_user = AsyncMock()
    return manager


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock MCP settings."""
    settings = MagicMock()
    settings.tool_execution_timeout = 30.0
    settings.blocked_tool_patterns = []
    settings.high_risk_tool_patterns = []
    return settings


@pytest.fixture
def executor(user_id: str, session_id, mock_ws_manager: MagicMock, mock_settings: MagicMock):
    """Create MCP tool executor."""
    with patch("agent.mcp.executor.get_mcp_settings", return_value=mock_settings):
        return McpToolExecutor(
            user_id=user_id,
            session_id=session_id,
            ws_manager=mock_ws_manager,
        )


class TestMcpToolCall:
    """Tests for McpToolCall class."""

    def test_create_tool_call(self):
        """Test creating a tool call."""
        server = _create_mock_server()
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={"param": "value"},
            mcp_server=server,
        )

        assert tool_call.tool_name == "test_tool"
        assert tool_call.tool_input == {"param": "value"}
        assert tool_call.mcp_server == server
        assert tool_call.request_id is not None


class TestMcpToolResult:
    """Tests for McpToolResult class."""

    def test_create_success_result(self):
        """Test creating a successful result."""
        result = McpToolResult(
            success=True,
            output={"data": "test"},
            execution_time_ms=100,
        )

        assert result.success is True
        assert result.output == {"data": "test"}
        assert result.error is None
        assert result.execution_time_ms == 100

    def test_create_error_result(self):
        """Test creating an error result."""
        result = McpToolResult(
            success=False,
            error="Something went wrong",
            execution_time_ms=50,
        )

        assert result.success is False
        assert result.output is None
        assert result.error == "Something went wrong"


class TestMcpToolExecutor:
    """Tests for McpToolExecutor class."""

    def test_should_require_approval_always(self, executor: McpToolExecutor):
        """Test approval required when set to always."""
        server = _create_mock_server(require_approval="always")
        assert executor._should_require_approval(server, "low") is True
        assert executor._should_require_approval(server, "medium") is True
        assert executor._should_require_approval(server, "high") is True

    def test_should_require_approval_never(self, executor: McpToolExecutor):
        """Test approval not required when set to never."""
        server = _create_mock_server(require_approval="never")
        assert executor._should_require_approval(server, "low") is False
        assert executor._should_require_approval(server, "medium") is False
        assert executor._should_require_approval(server, "high") is False

    def test_should_require_approval_conditional(self, executor: McpToolExecutor):
        """Test approval based on risk level when conditional."""
        server = _create_mock_server(require_approval="conditional")
        assert executor._should_require_approval(server, "low") is False
        assert executor._should_require_approval(server, "medium") is True
        assert executor._should_require_approval(server, "high") is True

    async def test_execute_tool_no_approval_needed(
        self,
        executor: McpToolExecutor,
        mock_settings: MagicMock,
    ):
        """Test executing tool without approval."""
        server = _create_mock_server(require_approval="never")
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={"param": "value"},
            mcp_server=server,
        )

        mock_result = McpToolResult(success=True, output={"result": "test"})

        with patch.object(executor, "_execute_remote_tool", return_value=mock_result) as mock_exec:
            with patch.object(executor.validator, "assess_tool_risk", return_value=("low", [])):
                result = await executor.execute_tool(tool_call)

        assert result.success is True
        mock_exec.assert_called_once_with(tool_call)

    async def test_execute_tool_approval_granted(
        self,
        executor: McpToolExecutor,
    ):
        """Test executing tool with approval granted."""
        server = _create_mock_server(require_approval="always")
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={"param": "value"},
            mcp_server=server,
        )

        mock_result = McpToolResult(success=True, output={"result": "test"})

        with patch.object(executor, "_execute_remote_tool", return_value=mock_result):
            with patch.object(executor, "_request_user_approval", return_value=True):
                with patch.object(executor.validator, "assess_tool_risk", return_value=("low", [])):
                    result = await executor.execute_tool(tool_call)

        assert result.success is True

    async def test_execute_tool_approval_rejected(
        self,
        executor: McpToolExecutor,
    ):
        """Test executing tool with approval rejected."""
        server = _create_mock_server(require_approval="always")
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={"param": "value"},
            mcp_server=server,
        )

        with patch.object(executor, "_request_user_approval", return_value=False):
            with patch.object(executor.validator, "assess_tool_risk", return_value=("low", [])):
                result = await executor.execute_tool(tool_call)

        assert result.success is False
        assert "rejected" in result.error.lower()

    async def test_execute_stdio_tool_no_ws_manager(self, user_id: str, session_id):
        """Test executing stdio tool without WebSocket manager."""
        with patch("agent.mcp.executor.get_mcp_settings") as mock_settings:
            mock_settings.return_value.tool_execution_timeout = 30.0
            mock_settings.return_value.blocked_tool_patterns = []
            mock_settings.return_value.high_risk_tool_patterns = []

            executor = McpToolExecutor(
                user_id=user_id,
                session_id=session_id,
                ws_manager=None,
            )

        server = _create_mock_server(transport_type="stdio", command="node", args=["server.js"])
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={},
            mcp_server=server,
        )

        result = await executor._execute_stdio_tool(tool_call)

        assert result.success is False
        assert "websocket" in result.error.lower()

    async def test_execute_stdio_tool_timeout(
        self,
        executor: McpToolExecutor,
        mock_ws_manager: MagicMock,
    ):
        """Test stdio tool execution timeout."""
        server = _create_mock_server(transport_type="stdio", command="node", args=["server.js"])
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={},
            mcp_server=server,
        )

        # Override timeout to very short
        executor.settings.tool_execution_timeout = 0.01

        result = await executor._execute_stdio_tool(tool_call)

        assert result.success is False
        assert "timeout" in result.error.lower()

    async def test_request_user_approval_no_ws(self, user_id: str, session_id):
        """Test requesting approval without WebSocket returns False."""
        with patch("agent.mcp.executor.get_mcp_settings") as mock_settings:
            mock_settings.return_value.tool_execution_timeout = 30.0
            mock_settings.return_value.blocked_tool_patterns = []
            mock_settings.return_value.high_risk_tool_patterns = []

            executor = McpToolExecutor(
                user_id=user_id,
                session_id=session_id,
                ws_manager=None,
            )

        server = _create_mock_server()
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={},
            mcp_server=server,
        )

        approved = await executor._request_user_approval(tool_call, "high", ["reason"])

        assert approved is False

    async def test_request_user_approval_timeout(
        self,
        executor: McpToolExecutor,
        mock_ws_manager: MagicMock,
    ):
        """Test approval request timeout."""
        server = _create_mock_server()
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={},
            mcp_server=server,
        )

        # Patch asyncio.wait_for to raise timeout
        with patch("asyncio.wait_for", side_effect=TimeoutError):
            approved = await executor._request_user_approval(tool_call, "high", ["reason"])

        assert approved is False

    def test_handle_stdio_response(self, executor: McpToolExecutor):
        """Test handling stdio tool response."""
        request_id = "test-request-id"

        # Create pending future
        future: asyncio.Future[McpToolResult] = asyncio.Future()
        executor._pending_stdio_calls[request_id] = future

        executor.handle_stdio_response(
            request_id=request_id,
            success=True,
            output={"result": "data"},
            execution_time_ms=100,
        )

        assert future.done()
        result = future.result()
        assert result.success is True
        assert result.output == {"result": "data"}

    def test_handle_stdio_response_no_pending(self, executor: McpToolExecutor):
        """Test handling response with no pending request."""
        # Should not raise error
        executor.handle_stdio_response(
            request_id="non-existent",
            success=True,
            output={},
        )

    def test_handle_approval_response(self, executor: McpToolExecutor):
        """Test handling approval response."""
        request_id = "test-approval-id"

        future: asyncio.Future[bool] = asyncio.Future()
        executor._pending_approvals[request_id] = future

        executor.handle_approval_response(request_id=request_id, approved=True)

        assert future.done()
        assert future.result() is True

    def test_handle_approval_response_rejected(self, executor: McpToolExecutor):
        """Test handling rejection response."""
        request_id = "test-approval-id"

        future: asyncio.Future[bool] = asyncio.Future()
        executor._pending_approvals[request_id] = future

        executor.handle_approval_response(request_id=request_id, approved=False)

        assert future.done()
        assert future.result() is False

    def test_handle_approval_response_no_pending(self, executor: McpToolExecutor):
        """Test handling approval with no pending request."""
        # Should not raise error
        executor.handle_approval_response(request_id="non-existent", approved=True)

    def test_extract_tool_output_text_content(self, executor: McpToolExecutor):
        """Test extracting output from text content."""
        mock_result = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Hello, world!"
        mock_result.content = [mock_content]

        output = executor._extract_tool_output(mock_result)

        assert output == {"result": "Hello, world!"}

    def test_extract_tool_output_binary_content(self, executor: McpToolExecutor):
        """Test extracting output from binary content."""
        mock_result = MagicMock()
        mock_content = MagicMock(spec=["data", "mimeType"])
        mock_content.data = b"binary data"
        mock_content.mimeType = "image/png"
        del mock_content.text  # Ensure no text attribute
        mock_result.content = [mock_content]

        output = executor._extract_tool_output(mock_result)

        assert "Binary data" in output["result"]

    def test_extract_tool_output_no_content(self, executor: McpToolExecutor):
        """Test extracting output when no content."""
        mock_result = MagicMock()
        mock_result.content = []

        output = executor._extract_tool_output(mock_result)

        assert "result" in output

    def test_extract_tool_output_multiple_text(self, executor: McpToolExecutor):
        """Test extracting output from multiple text contents."""
        mock_result = MagicMock()
        mock_content1 = MagicMock()
        mock_content1.text = "Line 1"
        mock_content2 = MagicMock()
        mock_content2.text = "Line 2"
        mock_result.content = [mock_content1, mock_content2]

        output = executor._extract_tool_output(mock_result)

        assert output == {"result": "Line 1\nLine 2"}

    async def test_execute_remote_tool_no_url(self, executor: McpToolExecutor):
        """Test executing remote tool without server URL."""
        server = _create_mock_server(server_url=None)
        server.server_url = None
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={},
            mcp_server=server,
        )

        result = await executor._execute_remote_tool(tool_call)

        assert result.success is False
        assert "No server URL" in result.error

    async def test_execute_remote_tool_auth_required_no_creds(self, executor: McpToolExecutor):
        """Test executing remote tool when auth required but no credentials."""
        server = _create_mock_server(auth_type="bearer")
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={},
            mcp_server=server,
        )

        with patch("agent.mcp.executor.build_mcp_auth_headers", return_value=None):
            result = await executor._execute_remote_tool(tool_call)

        assert result.success is False
        assert "Authentication" in result.error

    async def test_log_execution_no_session(self, executor: McpToolExecutor):
        """Test logging execution without database session."""
        server = _create_mock_server()
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={},
            mcp_server=server,
        )
        result = McpToolResult(success=True, output={})

        # Should not raise error
        await executor._log_execution(
            db_session=None,
            tool_call=tool_call,
            agent_type="worker",
            task_id=None,
            milestone_id=None,
            result=result,
            status="success",
            require_approval=False,
            approved=None,
        )

    async def test_log_execution_with_session(self, executor: McpToolExecutor):
        """Test logging execution with database session."""
        server = _create_mock_server()
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={},
            mcp_server=server,
        )
        result = McpToolResult(success=True, output={"data": "test"}, execution_time_ms=100)

        mock_session = AsyncMock()
        mock_log_repo = MagicMock()
        mock_log_repo.log_execution = AsyncMock()

        with patch("agent.mcp.executor.McpToolLogRepository", return_value=mock_log_repo):
            await executor._log_execution(
                db_session=mock_session,
                tool_call=tool_call,
                agent_type="worker",
                task_id=uuid4(),
                milestone_id=uuid4(),
                result=result,
                status="success",
                require_approval=False,
                approved=None,
            )

        mock_log_repo.log_execution.assert_called_once()

    async def test_log_execution_error(self, executor: McpToolExecutor):
        """Test logging execution when database error occurs."""
        server = _create_mock_server()
        tool_call = McpToolCall(
            tool_name="test_tool",
            tool_input={},
            mcp_server=server,
        )
        result = McpToolResult(success=True, output={})

        mock_session = AsyncMock()
        mock_log_repo = MagicMock()
        mock_log_repo.log_execution = AsyncMock(side_effect=Exception("DB error"))

        with patch("agent.mcp.executor.McpToolLogRepository", return_value=mock_log_repo):
            # Should not raise error
            await executor._log_execution(
                db_session=mock_session,
                tool_call=tool_call,
                agent_type="worker",
                task_id=None,
                milestone_id=None,
                result=result,
                status="success",
                require_approval=False,
                approved=None,
            )
