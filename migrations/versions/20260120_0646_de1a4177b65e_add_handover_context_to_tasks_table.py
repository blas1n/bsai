"""Add handover_context to tasks table

Revision ID: de1a4177b65e
Revises: 20260119_snapshots
Create Date: 2026-01-20 06:46:15.399062

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "de1a4177b65e"
down_revision: str | Sequence[str] | None = "20260119_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add handover_context column to tasks table
    # This stores the summary of completed milestones and artifacts
    # for the next task's Conductor to reference
    op.add_column("tasks", sa.Column("handover_context", sa.TEXT(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tasks", "handover_context")
