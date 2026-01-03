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

    async def update_status(self, task_id: UUID, status: str) -> Task | None:
        """Update task status.

        Args:
            task_id: Task UUID
            status: New status value

        Returns:
            Updated task or None if not found
        """
        return await self.update(task_id, status=status)

    async def complete_task(self, task_id: UUID, final_result: str) -> Task | None:
        """Mark task as completed with final result.

        Args:
            task_id: Task UUID
            final_result: Final task output

        Returns:
            Updated task or None if not found
        """
        return await self.update(task_id, status="completed", final_result=final_result)

    async def fail_task(self, task_id: UUID, error_message: str) -> Task | None:
        """Mark task as failed with error message.

        Args:
            task_id: Task UUID
            error_message: Error description

        Returns:
            Updated task or None if not found
        """
        return await self.update(task_id, status="failed", final_result=error_message)
