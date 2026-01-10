"""MCP tool executor for HTTP/SSE and stdio coordination.

This module handles the execution of MCP tools, routing them appropriately:
- HTTP/SSE tools: Executed directly by LiteLLM
- stdio tools: Coordinated via WebSocket with frontend
"""

from __future__ import annotations

import asyncio
import time
import traceback
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import httpx
import structlog
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from agent.api.config import get_mcp_settings
from agent.api.schemas.websocket import WSMessage, WSMessageType
from agent.db.models.mcp_server_config import McpServerConfig
from agent.db.repository.mcp_tool_log_repo import McpToolLogRepository
from agent.mcp.security import McpSecurityValidator, build_mcp_auth_headers

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from agent.api.websocket.manager import ConnectionManager

logger = structlog.get_logger()


class McpToolCall:
    """Represents a tool call to be executed."""

    def __init__(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        mcp_server: McpServerConfig,
    ):
        """Initialize tool call.

        Args:
            tool_name: Name of the tool to call
            tool_input: Input parameters for the tool
            mcp_server: MCP server configuration
        """
        self.request_id = str(uuid4())
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.mcp_server = mcp_server


class McpToolResult:
    """Result from MCP tool execution."""

    def __init__(
        self,
        success: bool,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        execution_time_ms: int | None = None,
    ):
        """Initialize tool result.

        Args:
            success: Whether execution succeeded
            output: Tool output if successful
            error: Error message if failed
            execution_time_ms: Execution time in milliseconds
        """
        self.success = success
        self.output = output
        self.error = error
        self.execution_time_ms = execution_time_ms


class McpToolExecutor:
    """Executor for MCP tool calls with approval and logging.

    Handles:
    - Tool approval workflow
    - HTTP/SSE tool execution (via LiteLLM)
    - stdio tool coordination (via WebSocket)
    - Execution logging
    """

    def __init__(
        self,
        user_id: str,
        session_id: UUID,
        ws_manager: ConnectionManager | None = None,
    ):
        """Initialize MCP tool executor.

        Args:
            user_id: User ID for ownership and logging
            session_id: Session ID for logging
            ws_manager: WebSocket manager for stdio coordination (optional)
        """
        self.user_id = user_id
        self.session_id = session_id
        self.ws_manager = ws_manager
        self.settings = get_mcp_settings()
        self.validator = McpSecurityValidator(self.settings)

        # Pending stdio calls (request_id -> Future)
        self._pending_stdio_calls: dict[str, asyncio.Future[McpToolResult]] = {}

        # Pending approvals (request_id -> Future[bool])
        self._pending_approvals: dict[str, asyncio.Future[bool]] = {}

    async def execute_tool(
        self,
        tool_call: McpToolCall,
        agent_type: str = "worker",
        db_session: AsyncSession | None = None,
        task_id: UUID | None = None,
        milestone_id: UUID | None = None,
    ) -> McpToolResult:
        """Execute a tool call with approval check and logging.

        Args:
            tool_call: Tool call to execute
            agent_type: Agent type ("worker" or "qa")
            db_session: Optional database session for logging
            task_id: Optional task ID for logging
            milestone_id: Optional milestone ID for logging

        Returns:
            Tool execution result
        """
        logger.info(
            "mcp_tool_call",
            tool_name=tool_call.tool_name,
            server=tool_call.mcp_server.name,
            transport=tool_call.mcp_server.transport_type,
            agent_type=agent_type,
        )

        # Assess tool risk
        risk_level, risk_reasons = self.validator.assess_tool_risk(
            tool_call.tool_name,
            tool_call.tool_input,
        )

        logger.info(
            "mcp_tool_risk_assessment",
            tool_name=tool_call.tool_name,
            risk_level=risk_level,
            reasons=risk_reasons,
        )

        # Check if approval required
        require_approval = self._should_require_approval(
            tool_call.mcp_server,
            risk_level,
        )

        approved = True
        if require_approval:
            logger.info("mcp_requesting_approval", tool_name=tool_call.tool_name)
            approved = await self._request_user_approval(
                tool_call,
                risk_level,
                risk_reasons,
            )

            if not approved:
                logger.warning("mcp_tool_rejected", tool_name=tool_call.tool_name)
                # Log rejection
                await self._log_execution(
                    db_session=db_session,
                    tool_call=tool_call,
                    agent_type=agent_type,
                    task_id=task_id,
                    milestone_id=milestone_id,
                    result=None,
                    status="rejected",
                    require_approval=require_approval,
                    approved=False,
                )
                return McpToolResult(
                    success=False,
                    error="Tool execution rejected by user",
                )

        # Execute based on transport type
        if tool_call.mcp_server.transport_type == "stdio":
            result = await self._execute_stdio_tool(tool_call)
        else:
            # HTTP/SSE handled by LiteLLM automatically
            result = await self._execute_remote_tool(tool_call)

        # Log execution
        await self._log_execution(
            db_session=db_session,
            tool_call=tool_call,
            agent_type=agent_type,
            task_id=task_id,
            milestone_id=milestone_id,
            result=result,
            status="success" if result.success else "error",
            require_approval=require_approval,
            approved=approved if require_approval else None,
        )

        return result

    async def _log_execution(
        self,
        db_session: AsyncSession | None,
        tool_call: McpToolCall,
        agent_type: str,
        task_id: UUID | None,
        milestone_id: UUID | None,
        result: McpToolResult | None,
        status: str,
        require_approval: bool,
        approved: bool | None,
    ) -> None:
        """Log tool execution to database.

        Args:
            db_session: Database session (if None, logging is skipped)
            tool_call: Tool call that was executed
            agent_type: Agent type ("worker" or "qa")
            task_id: Optional task ID
            milestone_id: Optional milestone ID
            result: Tool execution result (None if rejected)
            status: Execution status ("success", "error", "rejected")
            require_approval: Whether approval was required
            approved: Whether user approved (None if not required)
        """
        if not db_session:
            logger.debug(
                "mcp_logging_skipped",
                reason="no_db_session",
                tool_name=tool_call.tool_name,
            )
            return

        try:
            log_repo = McpToolLogRepository(db_session)
            await log_repo.log_execution(
                user_id=self.user_id,
                session_id=self.session_id,
                mcp_server_id=tool_call.mcp_server.id,
                tool_name=tool_call.tool_name,
                tool_input=tool_call.tool_input,
                agent_type=agent_type,
                status=status,
                required_approval=require_approval,
                task_id=task_id,
                milestone_id=milestone_id,
                tool_output=result.output if result else None,
                execution_time_ms=result.execution_time_ms if result else None,
                error_message=result.error if result else "Rejected by user",
                approved_by_user=approved,
            )
            logger.debug(
                "mcp_execution_logged",
                tool_name=tool_call.tool_name,
                status=status,
            )
        except Exception as e:
            logger.error(
                "mcp_logging_failed",
                tool_name=tool_call.tool_name,
                error=str(e),
            )

    def _should_require_approval(
        self,
        mcp_server: McpServerConfig,
        risk_level: str,
    ) -> bool:
        """Determine if tool requires user approval.

        Args:
            mcp_server: MCP server configuration
            risk_level: Risk level from assessment

        Returns:
            Whether approval is required
        """
        if mcp_server.require_approval == "always":
            return True
        elif mcp_server.require_approval == "never":
            return False
        else:  # "conditional"
            return risk_level in ["medium", "high"]

    async def _request_user_approval(
        self,
        tool_call: McpToolCall,
        risk_level: str,
        risk_reasons: list[str],
    ) -> bool:
        """Request user approval via WebSocket.

        Args:
            tool_call: Tool call requiring approval
            risk_level: Risk level assessment
            risk_reasons: Reasons for risk level

        Returns:
            Whether user approved the tool call
        """
        if not self.ws_manager:
            logger.warning(
                "mcp_approval_no_websocket",
                tool_name=tool_call.tool_name,
            )
            # Default to rejecting if no WebSocket available
            return False

        request_id = str(uuid4())

        # Create future for approval response
        approval_future: asyncio.Future[bool] = asyncio.Future()
        self._pending_approvals[request_id] = approval_future

        # Send approval request via WebSocket
        message = WSMessage(
            type=WSMessageType.MCP_APPROVAL_REQUEST,
            payload={
                "request_id": request_id,
                "session_id": str(self.session_id),
                "mcp_server_name": tool_call.mcp_server.name,
                "tool_name": tool_call.tool_name,
                "tool_input": tool_call.tool_input,
                "tool_description": f"Execute {tool_call.tool_name}",
                "risk_level": risk_level,
                "risk_reasons": risk_reasons,
            },
        )
        await self.ws_manager.broadcast_to_user(self.user_id, message)

        try:
            # Wait for approval (timeout after 60 seconds)
            approved = await asyncio.wait_for(approval_future, timeout=60.0)
            return approved
        except TimeoutError:
            logger.warning(
                "mcp_approval_timeout",
                tool_name=tool_call.tool_name,
                request_id=request_id,
            )
            return False
        finally:
            self._pending_approvals.pop(request_id, None)

    async def _execute_stdio_tool(
        self,
        tool_call: McpToolCall,
    ) -> McpToolResult:
        """Execute stdio tool via frontend WebSocket.

        Args:
            tool_call: Tool call to execute

        Returns:
            Tool execution result
        """
        if not self.ws_manager:
            logger.error(
                "mcp_stdio_no_websocket",
                tool_name=tool_call.tool_name,
            )
            return McpToolResult(
                success=False,
                error="WebSocket not available for stdio execution",
            )

        # Create future for tool result
        result_future: asyncio.Future[McpToolResult] = asyncio.Future()
        self._pending_stdio_calls[tool_call.request_id] = result_future

        # Send tool call request via WebSocket
        message = WSMessage(
            type=WSMessageType.MCP_TOOL_CALL_REQUEST,
            payload={
                "request_id": tool_call.request_id,
                "session_id": str(self.session_id),
                "mcp_server_id": str(tool_call.mcp_server.id),
                "mcp_server_name": tool_call.mcp_server.name,
                "tool_name": tool_call.tool_name,
                "tool_input": tool_call.tool_input,
                "stdio_config": {
                    "command": tool_call.mcp_server.command,
                    "args": tool_call.mcp_server.args or [],
                    "env_vars": tool_call.mcp_server.env_vars or {},
                },
                "require_approval": False,  # Already approved if we got here
            },
        )
        await self.ws_manager.broadcast_to_user(self.user_id, message)

        try:
            # Wait for result (timeout after tool execution timeout)
            result = await asyncio.wait_for(
                result_future,
                timeout=self.settings.tool_execution_timeout,
            )
            return result
        except TimeoutError:
            logger.error(
                "mcp_stdio_timeout",
                tool_name=tool_call.tool_name,
                request_id=tool_call.request_id,
            )
            return McpToolResult(
                success=False,
                error=f"Tool execution timeout ({self.settings.tool_execution_timeout}s)",
            )
        finally:
            self._pending_stdio_calls.pop(tool_call.request_id, None)

    async def _execute_remote_tool(
        self,
        tool_call: McpToolCall,
    ) -> McpToolResult:
        """Execute HTTP/SSE tool via MCP client.

        Connects to the MCP server and executes the tool call directly.

        Args:
            tool_call: Tool call to execute

        Returns:
            Tool execution result
        """
        logger.info(
            "mcp_remote_tool_execution",
            tool_name=tool_call.tool_name,
            server=tool_call.mcp_server.name,
        )

        server = tool_call.mcp_server
        start_time = time.time()

        # Check server URL
        if not server.server_url:
            return McpToolResult(
                success=False,
                error=f"No server URL configured for {server.name}",
            )

        # Build auth headers if configured
        headers = build_mcp_auth_headers(server, self.settings)

        # Check if auth is required but headers are missing
        if server.auth_type and server.auth_type != "none" and not headers:
            return McpToolResult(
                success=False,
                error="Authentication credentials are not configured or could not be decrypted.",
            )

        try:
            if server.transport_type == "sse":
                async with sse_client(url=server.server_url, headers=headers) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            tool_call.tool_name,
                            tool_call.tool_input,
                        )
                        execution_time_ms = int((time.time() - start_time) * 1000)

                        # Extract content from result
                        output = self._extract_tool_output(result)

                        logger.info(
                            "mcp_remote_tool_success",
                            tool_name=tool_call.tool_name,
                            execution_time_ms=execution_time_ms,
                        )

                        return McpToolResult(
                            success=True,
                            output=output,
                            execution_time_ms=execution_time_ms,
                        )
            else:  # http
                # Create httpx client with headers for authentication
                http_client = httpx.AsyncClient(headers=headers) if headers else None
                async with streamable_http_client(
                    url=server.server_url, http_client=http_client
                ) as (
                    read,
                    write,
                    _,
                ):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            tool_call.tool_name,
                            tool_call.tool_input,
                        )
                        execution_time_ms = int((time.time() - start_time) * 1000)

                        # Extract content from result
                        output = self._extract_tool_output(result)

                        logger.info(
                            "mcp_remote_tool_success",
                            tool_name=tool_call.tool_name,
                            execution_time_ms=execution_time_ms,
                        )

                        return McpToolResult(
                            success=True,
                            output=output,
                            execution_time_ms=execution_time_ms,
                        )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "mcp_remote_tool_error",
                tool_name=tool_call.tool_name,
                server=server.name,
                error=str(e),
                traceback=traceback.format_exc(),
            )
            return McpToolResult(
                success=False,
                error=str(e),
                execution_time_ms=execution_time_ms,
            )

    def _extract_tool_output(self, result: Any) -> dict[str, Any]:
        """Extract output from MCP tool result.

        Args:
            result: MCP CallToolResult

        Returns:
            Dictionary with tool output
        """
        # MCP result has content list with TextContent, ImageContent, etc.
        if hasattr(result, "content") and result.content:
            # Combine all text content
            text_parts = []
            for content in result.content:
                if hasattr(content, "text"):
                    text_parts.append(content.text)
                elif hasattr(content, "data"):
                    # Binary/image data - return as base64
                    text_parts.append(f"[Binary data: {content.mimeType}]")

            return {"result": "\n".join(text_parts) if text_parts else str(result)}

        return {"result": str(result)}

    def handle_stdio_response(
        self,
        request_id: str,
        success: bool,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        execution_time_ms: int | None = None,
    ) -> None:
        """Handle stdio tool execution response from frontend.

        Args:
            request_id: Request ID from original tool call
            success: Whether execution succeeded
            output: Tool output if successful
            error: Error message if failed
            execution_time_ms: Execution time in milliseconds
        """
        future = self._pending_stdio_calls.get(request_id)
        if future and not future.done():
            result = McpToolResult(
                success=success,
                output=output,
                error=error,
                execution_time_ms=execution_time_ms,
            )
            future.set_result(result)
        else:
            logger.warning(
                "mcp_stdio_response_no_pending",
                request_id=request_id,
            )

    def handle_approval_response(
        self,
        request_id: str,
        approved: bool,
    ) -> None:
        """Handle user approval response from frontend.

        Args:
            request_id: Request ID from approval request
            approved: Whether user approved
        """
        future = self._pending_approvals.get(request_id)
        if future and not future.done():
            future.set_result(approved)
        else:
            logger.warning(
                "mcp_approval_response_no_pending",
                request_id=request_id,
            )
