"""Add artifacts table

Revision ID: a1b2c3d4e5f6
Revises: ee8e2ece8955
Create Date: 2025-12-31 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "ee8e2ece8955"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create artifacts table."""
    op.create_table(
        "artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("milestone_id", sa.UUID(), nullable=True),
        sa.Column("artifact_type", sa.VARCHAR(length=20), nullable=False, server_default="code"),
        sa.Column("filename", sa.VARCHAR(length=255), nullable=False),
        sa.Column("language", sa.VARCHAR(length=50), nullable=True),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column("path", sa.VARCHAR(length=500), nullable=True),
        sa.Column("sequence_number", sa.INTEGER(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["milestone_id"], ["milestones.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_artifacts_task_id"), "artifacts", ["task_id"], unique=False)
    op.create_index(op.f("ix_artifacts_milestone_id"), "artifacts", ["milestone_id"], unique=False)


def downgrade() -> None:
    """Drop artifacts table."""
    op.drop_index(op.f("ix_artifacts_milestone_id"), table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_task_id"), table_name="artifacts")
    op.drop_table("artifacts")
