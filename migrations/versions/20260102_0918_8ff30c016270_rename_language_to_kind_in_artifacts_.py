"""Rename language to kind in artifacts table

Revision ID: 8ff30c016270
Revises: a1b2c3d4e5f6
Create Date: 2026-01-02 09:18:32.701074

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ff30c016270"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add kind column (nullable first for data migration)
    op.add_column("artifacts", sa.Column("kind", sa.VARCHAR(length=50), nullable=True))

    # Copy data from language to kind
    op.execute("UPDATE artifacts SET kind = COALESCE(language, 'txt')")

    # Make kind NOT NULL after data migration
    op.alter_column("artifacts", "kind", nullable=False)

    # Make path NOT NULL (set default for existing null values)
    op.execute("UPDATE artifacts SET path = '' WHERE path IS NULL")
    op.alter_column("artifacts", "path", existing_type=sa.VARCHAR(length=500), nullable=False)

    # Drop language column
    op.drop_column("artifacts", "language")


def downgrade() -> None:
    """Downgrade schema."""
    # Add language column back
    op.add_column("artifacts", sa.Column("language", sa.VARCHAR(length=50), nullable=True))

    # Copy data from kind to language
    op.execute("UPDATE artifacts SET language = kind")

    # Make path nullable again
    op.alter_column("artifacts", "path", existing_type=sa.VARCHAR(length=500), nullable=True)

    # Drop kind column
    op.drop_column("artifacts", "kind")
