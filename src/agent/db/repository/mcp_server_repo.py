"""MCP server configuration repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.mcp_server_config import McpServerConfig
from .base import BaseRepository


class McpServerRepository(BaseRepository[McpServerConfig]):
    """Repository for MCP server configuration operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize MCP server repository.

        Args:
            session: Database session
        """
        super().__init__(McpServerConfig, session)

    async def get_by_user(
        self,
        user_id: str,
        is_active_only: bool = True,
    ) -> list[McpServerConfig]:
        """Get all MCP servers for a user.

        Args:
            user_id: User identifier
            is_active_only: Filter only active servers

        Returns:
            List of MCP server configurations
        """
        stmt = select(McpServerConfig).where(McpServerConfig.user_id == user_id)

        if is_active_only:
            stmt = stmt.where(McpServerConfig.is_active == True)  # noqa: E712

        stmt = stmt.order_by(McpServerConfig.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_and_user(
        self,
        server_id: UUID,
        user_id: str,
    ) -> McpServerConfig | None:
        """Get MCP server by ID ensuring user ownership.

        Args:
            server_id: Server UUID
            user_id: User identifier

        Returns:
            MCP server configuration or None if not found or not owned by user
        """
        stmt = (
            select(McpServerConfig)
            .where(McpServerConfig.id == server_id)
            .where(McpServerConfig.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name_and_user(
        self,
        name: str,
        user_id: str,
    ) -> McpServerConfig | None:
        """Get MCP server by name and user.

        Args:
            name: Server name
            user_id: User identifier

        Returns:
            MCP server configuration or None if not found
        """
        stmt = (
            select(McpServerConfig)
            .where(McpServerConfig.name == name)
            .where(McpServerConfig.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_enabled_for_agent(
        self,
        user_id: str,
        agent_type: str,
    ) -> list[McpServerConfig]:
        """Get MCP servers enabled for a specific agent type.

        Args:
            user_id: User identifier
            agent_type: "worker" or "qa"

        Returns:
            List of enabled MCP server configurations
        """
        stmt = (
            select(McpServerConfig)
            .where(McpServerConfig.user_id == user_id)
            .where(McpServerConfig.is_active == True)  # noqa: E712
        )

        if agent_type == "worker":
            stmt = stmt.where(McpServerConfig.enabled_for_worker == True)  # noqa: E712
        elif agent_type == "qa":
            stmt = stmt.where(McpServerConfig.enabled_for_qa == True)  # noqa: E712

        stmt = stmt.order_by(McpServerConfig.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_by_user(
        self,
        server_id: UUID,
        user_id: str,
        **kwargs: Any,
    ) -> McpServerConfig | None:
        """Update MCP server ensuring user ownership.

        Args:
            server_id: Server UUID
            user_id: User identifier
            **kwargs: Attributes to update

        Returns:
            Updated MCP server configuration or None if not found or not owned
        """
        server = await self.get_by_id_and_user(server_id, user_id)
        if server is None:
            return None

        for key, value in kwargs.items():
            setattr(server, key, value)

        await self.session.flush()
        await self.session.refresh(server)
        return server

    async def delete_by_user(
        self,
        server_id: UUID,
        user_id: str,
    ) -> bool:
        """Soft delete MCP server ensuring user ownership.

        Args:
            server_id: Server UUID
            user_id: User identifier

        Returns:
            True if deleted, False if not found or not owned
        """
        server = await self.get_by_id_and_user(server_id, user_id)
        if server is None:
            return False

        server.is_active = False
        await self.session.flush()
        return True
