"""Artifact task-level snapshots

Revision ID: 20260119_snapshots
Revises: 20260115_1000
Create Date: 2026-01-19

Adds session_id column and converts artifacts to task-level snapshots:
- Adds session_id column (populated from task.session_id)
- Adds updated_at column
- task_id remains NOT NULL (snapshot identifier)
- Adds index on (task_id, path, filename) for snapshot queries
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260119_snapshots"
down_revision: str | Sequence[str] | None = "20260115_1000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade to task-level snapshots with session tracking.

    1. Add session_id column (populated from task.session_id)
    2. Add updated_at column
    3. Add index on (task_id, path, filename) for snapshot queries
    4. Add session_id foreign key
    """
    # 1. Add session_id column as nullable first
    op.add_column("artifacts", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.add_column(
        "artifacts",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    # 2. Populate session_id from task.session_id for existing records
    op.execute("""
        UPDATE artifacts
        SET session_id = tasks.session_id
        FROM tasks
        WHERE artifacts.task_id = tasks.id
    """)

    # 3. Make session_id NOT NULL after populating
    op.alter_column("artifacts", "session_id", nullable=False)

    # 4. Create indexes
    op.create_index(op.f("ix_artifacts_session_id"), "artifacts", ["session_id"], unique=False)
    op.create_index(
        "ix_artifacts_task_path_filename",
        "artifacts",
        ["task_id", "path", "filename"],
        unique=False,
    )

    # 5. Add session_id foreign key
    op.create_foreign_key(
        "artifacts_session_id_fkey",
        "artifacts",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade by removing session_id and task-based index."""
    # Drop session foreign key
    op.drop_constraint("artifacts_session_id_fkey", "artifacts", type_="foreignkey")

    # Drop indexes
    op.drop_index("ix_artifacts_task_path_filename", table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_session_id"), table_name="artifacts")

    # Drop new columns
    op.drop_column("artifacts", "updated_at")
    op.drop_column("artifacts", "session_id")
