"""LangGraph checkpointer configuration for state persistence.

Provides PostgreSQL-based checkpointing for workflow state persistence,
enabling pause/resume and interrupt functionality.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agent.api.config import get_database_settings

logger = structlog.get_logger()


@asynccontextmanager
async def get_checkpointer() -> AsyncGenerator[AsyncPostgresSaver, None]:
    """Get a checkpointer instance as a context manager.

    Uses the same database as the main application but with a
    dedicated connection for checkpointing operations.

    Yields:
        Configured AsyncPostgresSaver instance
    """
    settings = get_database_settings()

    # Convert asyncpg URL to psycopg format for langgraph-checkpoint-postgres
    # postgresql+asyncpg://... -> postgresql://...
    db_url = settings.database_url.replace("+asyncpg", "")

    async with AsyncPostgresSaver.from_conn_string(db_url) as checkpointer:
        # Setup the checkpointer tables (idempotent)
        await checkpointer.setup()

        logger.debug(
            "checkpointer_created",
            db_host=db_url.split("@")[-1].split("/")[0] if "@" in db_url else "unknown",
        )

        yield checkpointer
