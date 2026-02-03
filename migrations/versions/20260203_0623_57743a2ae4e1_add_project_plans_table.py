"""Add project_plans table

Revision ID: 57743a2ae4e1
Revises: 7a736f31dadb
Create Date: 2026-02-03 06:23:37.373248

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "57743a2ae4e1"
down_revision: str | Sequence[str] | None = "7a736f31dadb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create project_plans table with indexes."""
    op.create_table(
        "project_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.VARCHAR(length=255), nullable=False),
        sa.Column("overview", sa.TEXT(), nullable=True),
        sa.Column(
            "tech_stack",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("structure_type", sa.VARCHAR(length=20), server_default="flat", nullable=False),
        sa.Column(
            "plan_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("status", sa.VARCHAR(length=20), server_default="draft", nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.VARCHAR(length=255), nullable=True),
        sa.Column("total_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "breakpoint_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "qa_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
    )

    # Create indexes
    op.create_index("ix_project_plans_task_id", "project_plans", ["task_id"])
    op.create_index("ix_project_plans_session_id", "project_plans", ["session_id"])
    op.create_index("ix_project_plans_status", "project_plans", ["status"])


def downgrade() -> None:
    """Drop project_plans table and indexes."""
    op.drop_index("ix_project_plans_status", table_name="project_plans")
    op.drop_index("ix_project_plans_session_id", table_name="project_plans")
    op.drop_index("ix_project_plans_task_id", table_name="project_plans")
    op.drop_table("project_plans")
