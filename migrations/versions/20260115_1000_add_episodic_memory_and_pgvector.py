"""Add episodic memory with pgvector support

Revision ID: 20260115_1000
Revises: fd3b4221f251
Create Date: 2026-01-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260115_1000"
down_revision: str | Sequence[str] | None = "fd3b4221f251"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create episodic_memories table with pgvector support."""
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create episodic_memories table
    op.create_table(
        "episodic_memories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.VARCHAR(255), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column("summary", sa.TEXT(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("memory_type", sa.VARCHAR(50), nullable=False),
        sa.Column("importance_score", sa.FLOAT(), nullable=False, server_default="0.5"),
        sa.Column("access_count", sa.INTEGER(), nullable=False, server_default="0"),
        sa.Column("tags", postgresql.ARRAY(sa.VARCHAR(100)), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
    )

    # Create standard indexes
    op.create_index("ix_episodic_memories_user_id", "episodic_memories", ["user_id"])
    op.create_index("ix_episodic_memories_memory_type", "episodic_memories", ["memory_type"])
    op.create_index("ix_episodic_memories_session_id", "episodic_memories", ["session_id"])

    # Create vector index for cosine similarity (IVFFlat for performance)
    # Note: IVFFlat requires data to build properly, but we create it empty first
    # In production with large data, consider HNSW for better performance
    op.execute("""
        CREATE INDEX ix_episodic_memories_embedding
        ON episodic_memories
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)


def downgrade() -> None:
    """Drop episodic_memories table."""
    op.drop_index("ix_episodic_memories_embedding", table_name="episodic_memories")
    op.drop_index("ix_episodic_memories_session_id", table_name="episodic_memories")
    op.drop_index("ix_episodic_memories_memory_type", table_name="episodic_memories")
    op.drop_index("ix_episodic_memories_user_id", table_name="episodic_memories")
    op.drop_table("episodic_memories")
    # Note: We don't drop the vector extension as other tables might use it
