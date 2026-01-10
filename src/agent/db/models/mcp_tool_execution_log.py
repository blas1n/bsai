"""MCP tool execution log model."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import BOOLEAN, INTEGER, TEXT, VARCHAR, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .mcp_server_config import McpServerConfig
    from .milestone import Milestone
    from .session import Session
    from .task import Task


class McpToolExecutionLog(Base):
    """Audit log for MCP tool executions.

    Tracks every MCP tool call for security, debugging, and analytics.

    Attributes:
        id: Primary key (UUID)
        user_id: User identifier (indexed for per-user queries)
        session_id: Session FK
        task_id: Task FK (optional)
        milestone_id: Milestone FK (optional)
        mcp_server_id: MCP server FK

        # Tool information
        tool_name: Name of the tool called
        tool_input: Input parameters (JSONB)
        tool_output: Output result (JSONB, optional)

        # Execution metadata
        agent_type: "worker" | "qa"
        execution_time_ms: Execution duration
        status: "success" | "error" | "rejected"
        error_message: Error details if failed

        # Approval tracking
        required_approval: Whether approval was required
        approved_by_user: Whether user approved (null if no approval required)

        created_at: Execution timestamp
    """

    __tablename__ = "mcp_tool_execution_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(VARCHAR(255), index=True, nullable=False)

    # Foreign keys
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"))
    milestone_id: Mapped[UUID | None] = mapped_column(ForeignKey("milestones.id"))
    mcp_server_id: Mapped[UUID] = mapped_column(ForeignKey("mcp_server_configs.id"), nullable=False)

    # Tool information
    tool_name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    tool_input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tool_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Execution metadata
    agent_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)  # "worker" | "qa"
    execution_time_ms: Mapped[int | None] = mapped_column(INTEGER)
    status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False
    )  # "success" | "error" | "rejected"
    error_message: Mapped[str | None] = mapped_column(TEXT)

    # Approval tracking
    required_approval: Mapped[bool] = mapped_column(BOOLEAN, nullable=False)
    approved_by_user: Mapped[bool | None] = mapped_column(BOOLEAN)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    # Relationships
    session: Mapped["Session"] = relationship("Session", foreign_keys=[session_id])
    task: Mapped["Task | None"] = relationship("Task", foreign_keys=[task_id])
    milestone: Mapped["Milestone | None"] = relationship("Milestone", foreign_keys=[milestone_id])
    mcp_server: Mapped["McpServerConfig"] = relationship(
        "McpServerConfig", foreign_keys=[mcp_server_id]
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<McpToolExecutionLog(id={self.id}, tool={self.tool_name}, status={self.status}, agent={self.agent_type})>"
