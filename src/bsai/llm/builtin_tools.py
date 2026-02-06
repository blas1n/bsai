"""Built-in tools for Worker agent.

These tools are always available to Worker without requiring MCP server configuration.
They provide essential capabilities like reading session artifacts.

TODO: If built-in tools grow beyond 5, consider refactoring to:
  - Decorator-based registration pattern
  - Dictionary dispatch instead of if-elif chain in execute()
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from bsai.db.repository.artifact_repo import ArtifactRepository

logger = structlog.get_logger()


# Tool definitions in OpenAI function calling format
BUILTIN_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_artifact",
            "description": (
                "Read the full content of an existing artifact file from the session. "
                "Use this when you need to see the complete content of a file before modifying it. "
                "The file_path should match one from the artifact file list provided in context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path of the artifact file to read (e.g., 'src/app.js', 'index.html')",
                    }
                },
                "required": ["file_path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_artifacts",
            "description": (
                "List all artifact files in the current session with their sizes. "
                "Use this to see what files exist before deciding which to read or modify."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]

# Set of built-in tool names for quick lookup
BUILTIN_TOOL_NAMES = {tool["function"]["name"] for tool in BUILTIN_TOOL_DEFINITIONS}


class BuiltinToolExecutor:
    """Executor for built-in tools that don't require MCP servers.

    Built-in tools have direct database access and can query session data.
    """

    def __init__(
        self,
        session: AsyncSession,
        session_id: UUID,
        task_id: UUID,
    ):
        """Initialize built-in tool executor.

        Args:
            session: Database session for queries
            session_id: Current session ID
            task_id: Current task ID
        """
        self.db_session = session
        self.session_id = session_id
        self.task_id = task_id
        self.artifact_repo = ArtifactRepository(session)

    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a built-in tool.

        Args:
            tool_name: Name of the built-in tool
            tool_input: Input parameters for the tool

        Returns:
            Tool execution result
        """
        logger.info(
            "builtin_tool_execution",
            tool_name=tool_name,
            session_id=str(self.session_id),
        )

        if tool_name == "read_artifact":
            return await self._read_artifact(tool_input)
        elif tool_name == "list_artifacts":
            return await self._list_artifacts()
        else:
            return {"error": f"Unknown built-in tool: {tool_name}"}

    async def _read_artifact(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Read artifact content by file path.

        Args:
            tool_input: Contains 'file_path' key

        Returns:
            Artifact content or error
        """
        file_path = tool_input.get("file_path", "")
        if not file_path:
            return {"error": "file_path is required"}

        # Split path into directory and filename
        if "/" in file_path:
            path, filename = file_path.rsplit("/", 1)
        else:
            path = ""
            filename = file_path

        # Get latest snapshot and find the artifact
        artifacts = await self.artifact_repo.get_latest_snapshot(self.session_id)

        for artifact in artifacts:
            artifact_path = artifact.path or ""
            if artifact_path == path and artifact.filename == filename:
                logger.info(
                    "builtin_tool_read_artifact_success",
                    file_path=file_path,
                    content_length=len(artifact.content),
                )
                return {
                    "file_path": file_path,
                    "kind": artifact.kind,
                    "content": artifact.content,
                }

        logger.warning(
            "builtin_tool_read_artifact_not_found",
            file_path=file_path,
        )
        return {"error": f"Artifact not found: {file_path}"}

    async def _list_artifacts(self) -> dict[str, Any]:
        """List all artifacts in the session.

        Returns:
            List of artifact metadata
        """
        artifacts = await self.artifact_repo.get_latest_snapshot(self.session_id)

        file_list = []
        total_chars = 0

        for artifact in artifacts:
            file_path = (
                f"{artifact.path}/{artifact.filename}" if artifact.path else artifact.filename
            )
            file_list.append(
                {
                    "path": file_path,
                    "kind": artifact.kind,
                    "size": len(artifact.content),
                }
            )
            total_chars += len(artifact.content)

        logger.info(
            "builtin_tool_list_artifacts",
            file_count=len(file_list),
            total_chars=total_chars,
        )

        return {
            "files": file_list,
            "total_files": len(file_list),
            "total_characters": total_chars,
        }
