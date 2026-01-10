"""Add MCP support tables

Revision ID: 20260106_1500
Revises: 8ff30c016270
Create Date: 2026-01-06 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260106_1500"
down_revision: str | Sequence[str] | None = "8ff30c016270"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create MCP server config and tool execution log tables."""
    # Create mcp_server_configs table
    op.create_table(
        "mcp_server_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.VARCHAR(length=255), nullable=False),
        sa.Column("name", sa.VARCHAR(length=100), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=True),
        sa.Column("transport_type", sa.VARCHAR(length=20), nullable=False),
        sa.Column("server_url", sa.VARCHAR(length=500), nullable=True),
        sa.Column("auth_type", sa.VARCHAR(length=50), nullable=True),
        sa.Column("auth_credentials", sa.TEXT(), nullable=True),
        sa.Column("command", sa.TEXT(), nullable=True),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("env_vars", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("available_tools", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "require_approval", sa.VARCHAR(length=20), nullable=False, server_default="always"
        ),
        sa.Column(
            "enabled_for_worker", sa.BOOLEAN(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("enabled_for_qa", sa.BOOLEAN(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.BOOLEAN(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_user_mcp_server"),
    )
    op.create_index(
        "ix_mcp_server_configs_user_id", "mcp_server_configs", ["user_id"], unique=False
    )
    op.create_index(
        "ix_mcp_user_active", "mcp_server_configs", ["user_id", "is_active"], unique=False
    )

    # Create mcp_tool_execution_logs table
    op.create_table(
        "mcp_tool_execution_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.VARCHAR(length=255), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("milestone_id", sa.UUID(), nullable=True),
        sa.Column("mcp_server_id", sa.UUID(), nullable=False),
        sa.Column("tool_name", sa.VARCHAR(length=100), nullable=False),
        sa.Column("tool_input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tool_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agent_type", sa.VARCHAR(length=50), nullable=False),
        sa.Column("execution_time_ms", sa.INTEGER(), nullable=True),
        sa.Column("status", sa.VARCHAR(length=20), nullable=False),
        sa.Column("error_message", sa.TEXT(), nullable=True),
        sa.Column("required_approval", sa.BOOLEAN(), nullable=False),
        sa.Column("approved_by_user", sa.BOOLEAN(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["milestone_id"], ["milestones.id"]),
        sa.ForeignKeyConstraint(["mcp_server_id"], ["mcp_server_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mcp_tool_execution_logs_user_id", "mcp_tool_execution_logs", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Drop MCP tables."""
    op.drop_index("ix_mcp_tool_execution_logs_user_id", table_name="mcp_tool_execution_logs")
    op.drop_table("mcp_tool_execution_logs")
    op.drop_index("ix_mcp_user_active", table_name="mcp_server_configs")
    op.drop_index("ix_mcp_server_configs_user_id", table_name="mcp_server_configs")
    op.drop_table("mcp_server_configs")
