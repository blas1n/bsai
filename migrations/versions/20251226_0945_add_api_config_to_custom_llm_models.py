"""add_api_config_to_custom_llm_models

Revision ID: 20251226_0945
Revises: 20251226_0930
Create Date: 2025-12-26 09:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251226_0945"
down_revision: str | None = "20251226_0930"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add api_base and api_key columns to custom_llm_models table."""
    op.add_column(
        "custom_llm_models",
        sa.Column("api_base", sa.VARCHAR(length=500), nullable=True),
    )
    op.add_column(
        "custom_llm_models",
        sa.Column("api_key", sa.VARCHAR(length=500), nullable=True),
    )


def downgrade() -> None:
    """Remove api_base and api_key columns from custom_llm_models table."""
    op.drop_column("custom_llm_models", "api_key")
    op.drop_column("custom_llm_models", "api_base")
