"""Tests for BuiltinToolExecutor."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.llm.builtin_tools import (
    BUILTIN_TOOL_DEFINITIONS,
    BUILTIN_TOOL_NAMES,
    BuiltinToolExecutor,
)


class TestBuiltinToolDefinitions:
    """Tests for built-in tool definitions."""

    def test_tool_definitions_structure(self) -> None:
        """Test that tool definitions have correct structure."""
        assert len(BUILTIN_TOOL_DEFINITIONS) >= 2

        for tool in BUILTIN_TOOL_DEFINITIONS:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_builtin_tool_names(self) -> None:
        """Test that BUILTIN_TOOL_NAMES contains expected tools."""
        assert "read_artifact" in BUILTIN_TOOL_NAMES
        assert "list_artifacts" in BUILTIN_TOOL_NAMES

    def test_read_artifact_definition(self) -> None:
        """Test read_artifact tool definition."""
        read_artifact = next(
            t for t in BUILTIN_TOOL_DEFINITIONS if t["function"]["name"] == "read_artifact"
        )
        params = read_artifact["function"]["parameters"]
        assert "file_path" in params["properties"]
        assert "file_path" in params["required"]

    def test_list_artifacts_definition(self) -> None:
        """Test list_artifacts tool definition."""
        list_artifacts = next(
            t for t in BUILTIN_TOOL_DEFINITIONS if t["function"]["name"] == "list_artifacts"
        )
        params = list_artifacts["function"]["parameters"]
        assert params["required"] == []


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def session_id():
    """Create session ID."""
    return uuid4()


@pytest.fixture
def task_id():
    """Create task ID."""
    return uuid4()


@pytest.fixture
def executor(mock_session, session_id, task_id) -> BuiltinToolExecutor:
    """Create BuiltinToolExecutor instance."""
    return BuiltinToolExecutor(
        session=mock_session,
        session_id=session_id,
        task_id=task_id,
    )


class TestBuiltinToolExecutor:
    """Tests for BuiltinToolExecutor class."""

    def test_init(self, mock_session, session_id, task_id) -> None:
        """Test executor initialization."""
        executor = BuiltinToolExecutor(
            session=mock_session,
            session_id=session_id,
            task_id=task_id,
        )

        assert executor.db_session is mock_session
        assert executor.session_id == session_id
        assert executor.task_id == task_id
        assert executor.artifact_repo is not None

    async def test_execute_read_artifact(self, executor) -> None:
        """Test executing read_artifact tool."""
        mock_artifact = MagicMock()
        mock_artifact.path = "src"
        mock_artifact.filename = "main.py"
        mock_artifact.kind = "code"
        mock_artifact.content = "print('hello')"

        executor.artifact_repo.get_latest_snapshot = AsyncMock(return_value=[mock_artifact])

        result = await executor.execute(
            tool_name="read_artifact",
            tool_input={"file_path": "src/main.py"},
        )

        assert result["file_path"] == "src/main.py"
        assert result["kind"] == "code"
        assert result["content"] == "print('hello')"

    async def test_execute_read_artifact_no_path(self, executor) -> None:
        """Test reading artifact in root directory."""
        mock_artifact = MagicMock()
        mock_artifact.path = ""
        mock_artifact.filename = "index.html"
        mock_artifact.kind = "markup"
        mock_artifact.content = "<html></html>"

        executor.artifact_repo.get_latest_snapshot = AsyncMock(return_value=[mock_artifact])

        result = await executor.execute(
            tool_name="read_artifact",
            tool_input={"file_path": "index.html"},
        )

        assert result["file_path"] == "index.html"
        assert result["kind"] == "markup"

    async def test_execute_read_artifact_not_found(self, executor) -> None:
        """Test reading non-existent artifact."""
        executor.artifact_repo.get_latest_snapshot = AsyncMock(return_value=[])

        result = await executor.execute(
            tool_name="read_artifact",
            tool_input={"file_path": "nonexistent.py"},
        )

        assert "error" in result
        assert "not found" in result["error"].lower()

    async def test_execute_read_artifact_missing_file_path(self, executor) -> None:
        """Test read_artifact with missing file_path."""
        result = await executor.execute(
            tool_name="read_artifact",
            tool_input={},
        )

        assert "error" in result
        assert "file_path is required" in result["error"]

    async def test_execute_list_artifacts(self, executor) -> None:
        """Test executing list_artifacts tool."""
        mock_artifacts = [
            MagicMock(path="src", filename="main.py", kind="code", content="x = 1"),
            MagicMock(path="", filename="index.html", kind="markup", content="<html>"),
        ]

        executor.artifact_repo.get_latest_snapshot = AsyncMock(return_value=mock_artifacts)

        result = await executor.execute(
            tool_name="list_artifacts",
            tool_input={},
        )

        assert result["total_files"] == 2
        assert len(result["files"]) == 2
        assert result["total_characters"] == len("x = 1") + len("<html>")

        # Check file paths are correctly constructed
        paths = [f["path"] for f in result["files"]]
        assert "src/main.py" in paths
        assert "index.html" in paths

    async def test_execute_list_artifacts_empty(self, executor) -> None:
        """Test listing artifacts when none exist."""
        executor.artifact_repo.get_latest_snapshot = AsyncMock(return_value=[])

        result = await executor.execute(
            tool_name="list_artifacts",
            tool_input={},
        )

        assert result["total_files"] == 0
        assert result["files"] == []
        assert result["total_characters"] == 0

    async def test_execute_unknown_tool(self, executor) -> None:
        """Test executing unknown tool returns error."""
        result = await executor.execute(
            tool_name="unknown_tool",
            tool_input={},
        )

        assert "error" in result
        assert "Unknown built-in tool" in result["error"]

    async def test_read_artifact_with_nested_path(self, executor) -> None:
        """Test reading artifact with deeply nested path."""
        mock_artifact = MagicMock()
        mock_artifact.path = "src/components/ui"
        mock_artifact.filename = "Button.tsx"
        mock_artifact.kind = "code"
        mock_artifact.content = "export const Button = () => {}"

        executor.artifact_repo.get_latest_snapshot = AsyncMock(return_value=[mock_artifact])

        result = await executor.execute(
            tool_name="read_artifact",
            tool_input={"file_path": "src/components/ui/Button.tsx"},
        )

        assert result["file_path"] == "src/components/ui/Button.tsx"
        assert result["content"] == "export const Button = () => {}"
