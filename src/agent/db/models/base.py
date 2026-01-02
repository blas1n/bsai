"""SQLAlchemy declarative base for all models."""

from uuid import UUID

from sqlalchemy import Column
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models.

    Includes:
    - AsyncAttrs for async attribute loading
    - DeclarativeBase for SQLAlchemy 2.0 declarative mapping
    """

    # Declare id attribute for type checking (actual column defined in subclasses)
    @declared_attr
    def id(cls) -> Column[UUID]:
        """Primary key column - must be overridden in subclasses."""
        raise NotImplementedError("Subclasses must define id column")
