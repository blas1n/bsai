"""Convert episodic_memories timestamps to timezone-aware (TIMESTAMPTZ)

Revision ID: 7a736f31dadb
Revises: 20260120_milestone_seq
Create Date: 2026-01-23 02:37:20.966370

This migration converts the created_at and last_accessed_at columns in
episodic_memories from TIMESTAMP (naive) to TIMESTAMPTZ (timezone-aware).

Existing data is assumed to be in UTC and will be converted accordingly.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a736f31dadb"
down_revision: str | Sequence[str] | None = "20260120_milestone_seq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert timestamp columns to timestamptz (timezone-aware).

    PostgreSQL automatically converts existing TIMESTAMP values to TIMESTAMPTZ
    by assuming they are in the database's timezone (typically UTC).
    """
    op.execute("""
        ALTER TABLE episodic_memories
        ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'
    """)
    op.execute("""
        ALTER TABLE episodic_memories
        ALTER COLUMN last_accessed_at TYPE TIMESTAMPTZ USING last_accessed_at AT TIME ZONE 'UTC'
    """)


def downgrade() -> None:
    """Convert timestamptz columns back to timestamp (naive).

    Converts to UTC and strips timezone information.
    """
    op.execute("""
        ALTER TABLE episodic_memories
        ALTER COLUMN created_at TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC'
    """)
    op.execute("""
        ALTER TABLE episodic_memories
        ALTER COLUMN last_accessed_at TYPE TIMESTAMP USING last_accessed_at AT TIME ZONE 'UTC'
    """)
