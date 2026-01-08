"""MCP server configuration model."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BOOLEAN, TEXT, VARCHAR, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class McpServerConfig(Base):
    """MCP (Model Context Protocol) server configurations per user.

    Stores configuration for both remote (HTTP/SSE) and local (stdio) MCP servers.
    Local stdio servers are executed by frontend (native apps), while HTTP/SSE
    servers are executed by backend via LiteLLM.

    Attributes:
        id: Primary key (UUID)
        user_id: User identifier (indexed for per-user isolation)
        name: Server name (unique per user)
        description: Optional description
        transport_type: "stdio" | "http" | "sse"

        # HTTP/SSE specific (backend execution)
        server_url: HTTP/SSE server endpoint
        auth_type: "bearer" | "api_key" | "oauth2" | "basic" | "none"
        auth_credentials: Encrypted JSON credentials

        # stdio specific (frontend execution, reference only)
        command: Executable command
        args: Command arguments
        env_vars: Environment variables

        # Configuration
        available_tools: Optional filter for specific tools
        require_approval: "always" | "never" | "conditional"
        enabled_for_worker: Enable for Worker Agent
        enabled_for_qa: Enable for QA Agent
        is_active: Soft delete flag

        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "mcp_server_configs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(VARCHAR(255), index=True, nullable=False)

    # Server identification
    name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    description: Mapped[str | None] = mapped_column(TEXT)

    # Transport configuration
    transport_type: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False
    )  # "stdio" | "http" | "sse"

    # HTTP/SSE specific (executed by backend)
    server_url: Mapped[str | None] = mapped_column(VARCHAR(500))
    auth_type: Mapped[str | None] = mapped_column(
        VARCHAR(50)
    )  # "bearer" | "api_key" | "oauth2" | "basic" | "none"
    auth_credentials: Mapped[str | None] = mapped_column(TEXT)  # Encrypted JSON

    # stdio specific (executed by frontend, stored for reference)
    command: Mapped[str | None] = mapped_column(TEXT)
    args: Mapped[list[str] | None] = mapped_column(JSONB)
    env_vars: Mapped[dict[str, str] | None] = mapped_column(JSONB)

    # Tool configuration
    available_tools: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    require_approval: Mapped[str] = mapped_column(
        VARCHAR(20), default="always", nullable=False
    )  # "always" | "never" | "conditional"

    # Agent scope restriction
    enabled_for_worker: Mapped[bool] = mapped_column(BOOLEAN, default=True, nullable=False)
    enabled_for_qa: Mapped[bool] = mapped_column(BOOLEAN, default=True, nullable=False)

    # Metadata
    is_active: Mapped[bool] = mapped_column(BOOLEAN, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_mcp_server"),
        Index("ix_mcp_user_active", "user_id", "is_active"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<McpServerConfig(id={self.id}, user_id={self.user_id}, name={self.name}, transport={self.transport_type})>"
