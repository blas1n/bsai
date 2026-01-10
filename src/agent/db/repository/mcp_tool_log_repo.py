"""MCP tool execution log repository."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.mcp_tool_execution_log import McpToolExecutionLog
from .base import BaseRepository


class McpToolLogRepository(BaseRepository[McpToolExecutionLog]):
    """Repository for MCP tool execution log operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize MCP tool log repository.

        Args:
            session: Database session
        """
        super().__init__(McpToolExecutionLog, session)

    async def log_execution(
        self,
        user_id: str,
        session_id: UUID,
        mcp_server_id: UUID,
        tool_name: str,
        tool_input: dict[str, Any],
        agent_type: str,
        status: str,
        required_approval: bool,
        task_id: UUID | None = None,
        milestone_id: UUID | None = None,
        tool_output: dict[str, Any] | None = None,
        execution_time_ms: int | None = None,
        error_message: str | None = None,
        approved_by_user: bool | None = None,
    ) -> McpToolExecutionLog:
        """Create a tool execution log entry.

        Args:
            user_id: User identifier
            session_id: Session UUID
            mcp_server_id: MCP server UUID
            tool_name: Tool name
            tool_input: Tool input parameters
            agent_type: "worker" or "qa"
            status: "success" | "error" | "rejected"
            required_approval: Whether approval was required
            task_id: Optional task UUID
            milestone_id: Optional milestone UUID
            tool_output: Optional tool output
            execution_time_ms: Optional execution time
            error_message: Optional error message
            approved_by_user: Optional approval status

        Returns:
            Created tool execution log
        """
        return await self.create(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            mcp_server_id=mcp_server_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            agent_type=agent_type,
            execution_time_ms=execution_time_ms,
            status=status,
            error_message=error_message,
            required_approval=required_approval,
            approved_by_user=approved_by_user,
        )

    async def get_by_session(
        self,
        session_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[McpToolExecutionLog]:
        """Get tool execution logs for a session.

        Args:
            session_id: Session UUID
            limit: Maximum number of logs to return
            offset: Number of logs to skip

        Returns:
            List of tool execution logs ordered by creation time (newest first)
        """
        stmt = (
            select(McpToolExecutionLog)
            .where(McpToolExecutionLog.session_id == session_id)
            .order_by(McpToolExecutionLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_user(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
        status_filter: str | None = None,
        agent_type_filter: str | None = None,
    ) -> list[McpToolExecutionLog]:
        """Get tool execution logs for a user.

        Args:
            user_id: User identifier
            limit: Maximum number of logs to return
            offset: Number of logs to skip
            status_filter: Optional status filter ("success" | "error" | "rejected")
            agent_type_filter: Optional agent type filter ("worker" | "qa")

        Returns:
            List of tool execution logs ordered by creation time (newest first)
        """
        stmt = select(McpToolExecutionLog).where(McpToolExecutionLog.user_id == user_id)

        if status_filter:
            stmt = stmt.where(McpToolExecutionLog.status == status_filter)

        if agent_type_filter:
            stmt = stmt.where(McpToolExecutionLog.agent_type == agent_type_filter)

        stmt = stmt.order_by(McpToolExecutionLog.created_at.desc()).limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_mcp_server(
        self,
        mcp_server_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[McpToolExecutionLog]:
        """Get tool execution logs for a specific MCP server.

        Args:
            mcp_server_id: MCP server UUID
            limit: Maximum number of logs to return
            offset: Number of logs to skip

        Returns:
            List of tool execution logs ordered by creation time (newest first)
        """
        stmt = (
            select(McpToolExecutionLog)
            .where(McpToolExecutionLog.mcp_server_id == mcp_server_id)
            .order_by(McpToolExecutionLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_error_count_by_server(
        self,
        mcp_server_id: UUID,
        since: datetime | None = None,
    ) -> int:
        """Get error count for an MCP server.

        Args:
            mcp_server_id: MCP server UUID
            since: Optional datetime to count errors since

        Returns:
            Number of failed tool executions
        """
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(McpToolExecutionLog)
            .where(McpToolExecutionLog.mcp_server_id == mcp_server_id)
            .where(McpToolExecutionLog.status == "error")
        )

        if since:
            stmt = stmt.where(McpToolExecutionLog.created_at >= since)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def count_by_user(
        self,
        user_id: str,
        status_filter: str | None = None,
        agent_type_filter: str | None = None,
    ) -> int:
        """Count tool execution logs for a user.

        Args:
            user_id: User identifier
            status_filter: Optional status filter ("success" | "error" | "rejected")
            agent_type_filter: Optional agent type filter ("worker" | "qa")

        Returns:
            Total count of matching logs
        """
        stmt = (
            select(func.count())
            .select_from(McpToolExecutionLog)
            .where(McpToolExecutionLog.user_id == user_id)
        )

        if status_filter:
            stmt = stmt.where(McpToolExecutionLog.status == status_filter)

        if agent_type_filter:
            stmt = stmt.where(McpToolExecutionLog.agent_type == agent_type_filter)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def count_by_session(self, session_id: UUID) -> int:
        """Count tool execution logs for a session.

        Args:
            session_id: Session UUID

        Returns:
            Total count of logs for the session
        """
        stmt = (
            select(func.count())
            .select_from(McpToolExecutionLog)
            .where(McpToolExecutionLog.session_id == session_id)
        )

        result = await self.session.execute(stmt)
        return result.scalar_one()
