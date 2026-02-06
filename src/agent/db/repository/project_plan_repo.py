"""Repository for ProjectPlan database operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.project_plan import ProjectPlan
from .base import BaseRepository


class ProjectPlanRepository(BaseRepository[ProjectPlan]):
    """Repository for ProjectPlan CRUD operations.

    Note: This repository only handles data access.
    Business logic (status transitions, task counting, etc.)
    should be handled in the service layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository.

        Args:
            session: Database session
        """
        super().__init__(ProjectPlan, session)

    async def get_by_task_id(self, task_id: UUID) -> ProjectPlan | None:
        """Get project plan by task ID.

        Args:
            task_id: Task UUID

        Returns:
            ProjectPlan or None if not found
        """
        stmt = select(ProjectPlan).where(ProjectPlan.task_id == task_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_session_id(self, session_id: UUID) -> list[ProjectPlan]:
        """Get all project plans for a session.

        Args:
            session_id: Session UUID

        Returns:
            List of ProjectPlan instances ordered by creation time (newest first)
        """
        stmt = (
            select(ProjectPlan)
            .where(ProjectPlan.session_id == session_id)
            .order_by(ProjectPlan.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(
        self,
        status: str,
        session_id: UUID | None = None,
    ) -> list[ProjectPlan]:
        """Get project plans by status.

        Args:
            status: Plan status (draft, approved, in_progress, completed, rejected)
            session_id: Optional session filter

        Returns:
            List of ProjectPlan instances
        """
        stmt = select(ProjectPlan).where(ProjectPlan.status == status)

        if session_id is not None:
            stmt = stmt.where(ProjectPlan.session_id == session_id)

        stmt = stmt.order_by(ProjectPlan.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
