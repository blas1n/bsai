"""Add agent_steps table and milestone duration

Revision ID: fd3b4221f251
Revises: 20260106_1500
Create Date: 2026-01-11 13:13:36.279184

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fd3b4221f251"
down_revision: str | Sequence[str] | None = "20260106_1500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create agent_steps table and add duration columns to milestones."""
    # Create agent_steps table
    op.create_table(
        "agent_steps",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("milestone_id", sa.UUID(), nullable=True),
        sa.Column("agent_type", sa.VARCHAR(length=50), nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.INTEGER(), nullable=True),
        sa.Column("input_summary", sa.TEXT(), nullable=True),
        sa.Column("output_summary", sa.TEXT(), nullable=True),
        sa.Column("input_tokens", sa.INTEGER(), nullable=False),
        sa.Column("output_tokens", sa.INTEGER(), nullable=False),
        sa.Column("cost_usd", sa.DECIMAL(precision=10, scale=6), nullable=False),
        sa.Column("error_message", sa.TEXT(), nullable=True),
        sa.Column("metadata_json", sa.TEXT(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["milestone_id"], ["milestones.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_steps_agent_type"), "agent_steps", ["agent_type"], unique=False)
    op.create_index(
        op.f("ix_agent_steps_milestone_id"), "agent_steps", ["milestone_id"], unique=False
    )
    op.create_index(op.f("ix_agent_steps_status"), "agent_steps", ["status"], unique=False)
    op.create_index(op.f("ix_agent_steps_task_id"), "agent_steps", ["task_id"], unique=False)

    # Add duration columns to milestones
    op.add_column("milestones", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.add_column("milestones", sa.Column("ended_at", sa.DateTime(), nullable=True))
    op.add_column("milestones", sa.Column("duration_ms", sa.INTEGER(), nullable=True))


def downgrade() -> None:
    """Drop agent_steps table and remove duration columns from milestones."""
    # Remove milestone duration columns
    op.drop_column("milestones", "duration_ms")
    op.drop_column("milestones", "ended_at")
    op.drop_column("milestones", "started_at")

    # Drop agent_steps table
    op.drop_index(op.f("ix_agent_steps_task_id"), table_name="agent_steps")
    op.drop_index(op.f("ix_agent_steps_status"), table_name="agent_steps")
    op.drop_index(op.f("ix_agent_steps_milestone_id"), table_name="agent_steps")
    op.drop_index(op.f("ix_agent_steps_agent_type"), table_name="agent_steps")
    op.drop_table("agent_steps")
