"""Task repository for task-specific operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.task import Task
from .base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    """Repository for Task model operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize task repository.

        Args:
            session: Database session
        """
        super().__init__(Task, session)

    async def get_by_session_id(
        self,
        session_id: UUID,
        limit: int = 50,
        offset: int = 0,
        oldest_first: bool = False,
    ) -> list[Task]:
        """Get tasks by session ID.

        Args:
            session_id: Session UUID
            limit: Maximum number of tasks to return
            offset: Number of tasks to skip
            oldest_first: If True, order by oldest first (asc), otherwise newest first (desc)

        Returns:
            List of tasks for the session
        """
        order = Task.created_at.asc() if oldest_first else Task.created_at.desc()
        stmt = (
            select(Task)
            .where(Task.session_id == session_id)
            .order_by(order)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_milestones(self, task_id: UUID) -> Task | None:
        """Get task with all milestones eagerly loaded.

        Args:
            task_id: Task UUID

        Returns:
            Task with milestones or None if not found
        """
        stmt = select(Task).where(Task.id == task_id).options(selectinload(Task.milestones))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_session(self, task_id: UUID) -> Task | None:
        """Get task with session eagerly loaded.

        Args:
            task_id: Task UUID

        Returns:
            Task with session or None if not found
        """
        stmt = select(Task).where(Task.id == task_id).options(selectinload(Task.session))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_tasks(self, session_id: UUID | None = None) -> list[Task]:
        """Get all pending tasks, optionally filtered by session.

        Args:
            session_id: Optional session ID filter

        Returns:
            List of pending tasks
        """
        stmt = select(Task).where(Task.status == "pending")

        if session_id is not None:
            stmt = stmt.where(Task.session_id == session_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_handover_context(self, task_id: UUID, handover_context: str) -> Task | None:
        """Save handover context for next task's Architect.

        Args:
            task_id: Task UUID
            handover_context: Summary of completed work and artifacts

        Returns:
            Updated task or None if not found
        """
        return await self.update(task_id, handover_context=handover_context)

    async def get_previous_task_handover(self, session_id: UUID) -> str | None:
        """Get handover context from the most recent completed task in the session.

        Args:
            session_id: Session UUID

        Returns:
            Handover context string or None if no previous completed task
        """
        stmt = (
            select(Task.handover_context)
            .where(Task.session_id == session_id)
            .where(Task.status == "completed")
            .where(Task.handover_context.isnot(None))
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
