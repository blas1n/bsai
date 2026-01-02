"""Artifact repository for artifact-specific operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.artifact import Artifact
from .base import BaseRepository


class ArtifactRepository(BaseRepository[Artifact]):
    """Repository for Artifact model operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize artifact repository.

        Args:
            session: Database session
        """
        super().__init__(Artifact, session)

    async def get_by_task_id(self, task_id: UUID) -> list[Artifact]:
        """Get artifacts by task ID, ordered by sequence.

        Args:
            task_id: Task UUID

        Returns:
            List of artifacts ordered by sequence_number
        """
        stmt = (
            select(Artifact)
            .where(Artifact.task_id == task_id)
            .order_by(Artifact.sequence_number.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_milestone_id(self, milestone_id: UUID) -> list[Artifact]:
        """Get artifacts by milestone ID, ordered by sequence.

        Args:
            milestone_id: Milestone UUID

        Returns:
            List of artifacts ordered by sequence_number
        """
        stmt = (
            select(Artifact)
            .where(Artifact.milestone_id == milestone_id)
            .order_by(Artifact.sequence_number.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_artifact(
        self,
        task_id: UUID,
        artifact_type: str,
        filename: str,
        content: str,
        kind: str,
        path: str,
        milestone_id: UUID | None = None,
        sequence_number: int = 0,
    ) -> Artifact:
        """Create a new artifact.

        Args:
            task_id: Parent task UUID
            artifact_type: Type of artifact (code, file, document)
            filename: Filename or identifier
            content: Full content of the artifact
            kind: File type/extension (e.g., 'js', 'py', 'html', 'md')
            path: File path within project
            milestone_id: Optional milestone UUID
            sequence_number: Order within task

        Returns:
            Created artifact
        """
        artifact = Artifact(
            task_id=task_id,
            milestone_id=milestone_id,
            artifact_type=artifact_type,
            filename=filename,
            kind=kind,
            content=content,
            path=path,
            sequence_number=sequence_number,
        )
        self.session.add(artifact)
        await self.session.flush()
        await self.session.refresh(artifact)
        return artifact

    async def delete_by_task_id(self, task_id: UUID) -> int:
        """Delete all artifacts for a task.

        Args:
            task_id: Task UUID

        Returns:
            Number of artifacts deleted
        """
        artifacts = await self.get_by_task_id(task_id)
        count = len(artifacts)
        for artifact in artifacts:
            await self.session.delete(artifact)
        await self.session.flush()
        return count

    async def get_code_artifacts(self, task_id: UUID) -> list[Artifact]:
        """Get only code artifacts for a task.

        Args:
            task_id: Task UUID

        Returns:
            List of code artifacts
        """
        stmt = (
            select(Artifact)
            .where(Artifact.task_id == task_id, Artifact.artifact_type == "code")
            .order_by(Artifact.sequence_number.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
