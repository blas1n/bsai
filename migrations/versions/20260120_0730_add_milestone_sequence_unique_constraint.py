"""Add unique constraint on milestone (task_id, sequence_number)

Revision ID: 20260120_milestone_seq
Revises: de1a4177b65e
Create Date: 2026-01-20 07:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260120_milestone_seq"
down_revision: str | Sequence[str] | None = "de1a4177b65e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add unique constraint to prevent duplicate sequence numbers within a task
    # This ensures data integrity for milestone ordering
    op.create_unique_constraint(
        "uq_milestone_task_sequence",
        "milestones",
        ["task_id", "sequence_number"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_milestone_task_sequence", "milestones", type_="unique")
