"""SQLAlchemy declarative base for all models."""

from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models.

    Includes:
    - AsyncAttrs for async attribute loading
    - DeclarativeBase for SQLAlchemy 2.0 declarative mapping
    """

    pass
