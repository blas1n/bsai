"""add_custom_llm_models_table

Revision ID: 20251226_0930
Revises: 202512260810
Create Date: 2025-12-26 09:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20251226_0930"
down_revision: str | None = "202512260810"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create custom_llm_models table for user-defined models."""
    op.create_table(
        "custom_llm_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(length=100), nullable=False),
        sa.Column("provider", sa.VARCHAR(length=50), nullable=False),
        sa.Column("input_price_per_1k", sa.DECIMAL(precision=12, scale=8), nullable=False),
        sa.Column("output_price_per_1k", sa.DECIMAL(precision=12, scale=8), nullable=False),
        sa.Column("context_window", sa.INTEGER(), nullable=False),
        sa.Column("supports_streaming", sa.BOOLEAN(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_custom_llm_models_name"), "custom_llm_models", ["name"], unique=False)


def downgrade() -> None:
    """Drop custom_llm_models table."""
    op.drop_index(op.f("ix_custom_llm_models_name"), table_name="custom_llm_models")
    op.drop_table("custom_llm_models")
