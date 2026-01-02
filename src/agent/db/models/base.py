"""SQLAlchemy declarative base for all models."""

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Mapped


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models.

    Includes:
    - AsyncAttrs for async attribute loading
    - DeclarativeBase for SQLAlchemy 2.0 declarative mapping

    All subclasses must define an `id` column as primary key.
    """

    id: Mapped[UUID]
