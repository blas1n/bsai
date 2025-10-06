"""
PostgreSQL database connection
"""

from typing import Any
import databases
import sqlalchemy
from agent_platform.core.config import settings


# Database instance
database = databases.Database(str(settings.DATABASE_URL))

# SQLAlchemy metadata
metadata = sqlalchemy.MetaData()

# SQLAlchemy engine (for migrations)
engine = sqlalchemy.create_engine(
    str(settings.DATABASE_URL).replace("+asyncpg", ""),  # Sync connection for migrations
)


async def execute(query: str, *args: Any) -> Any:
    """Execute a query"""
    return await database.execute(query, *args)


async def fetch_all(query: str, *args: Any) -> list:
    """Fetch all rows"""
    return await database.fetch_all(query, *args)


async def fetch_one(query: str, *args: Any) -> Any:
    """Fetch one row"""
    return await database.fetch_one(query, *args)
