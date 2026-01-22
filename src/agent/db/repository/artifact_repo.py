"""Artifact repository for task-level snapshot operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.artifact import Artifact
from ..models.enums import TaskStatus
from ..models.task import Task
from .base import BaseRepository


class ArtifactRepository(BaseRepository[Artifact]):
    """Repository for Artifact model operations.

    Artifacts are managed at TASK level as snapshots.
    Each task creates a complete snapshot of all artifacts at that point.
    The task_id identifies which snapshot the artifact belongs to.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize artifact repository.

        Args:
            session: Database session
        """
        super().__init__(Artifact, session)

    async def get_by_task_id(self, task_id: UUID, limit: int = 1000) -> list[Artifact]:
        """Get all artifacts for a specific task (snapshot).

        Args:
            task_id: Task UUID (snapshot identifier)
            limit: Maximum number of artifacts to return

        Returns:
            List of artifacts in this task's snapshot
        """
        stmt = (
            select(Artifact)
            .where(Artifact.task_id == task_id)
            .order_by(Artifact.sequence_number.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_snapshot(self, session_id: UUID) -> list[Artifact]:
        """Get artifacts from the most recent completed task in session.

        This represents the "current" artifact state for the session.

        Args:
            session_id: Session UUID

        Returns:
            List of artifacts from latest completed task snapshot
        """
        # Find latest completed task
        latest_task_stmt = (
            select(Task.id)
            .where(Task.session_id == session_id)
            .where(Task.status == TaskStatus.COMPLETED.value)
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(latest_task_stmt)
        latest_task_id = result.scalar_one_or_none()

        if not latest_task_id:
            return []

        return await self.get_by_task_id(latest_task_id)

    async def get_by_session_id(self, session_id: UUID, limit: int = 1000) -> list[Artifact]:
        """Get latest snapshot artifacts for a session.

        This is an alias for get_latest_snapshot for API compatibility.

        Args:
            session_id: Session UUID
            limit: Maximum number of artifacts (applied after getting snapshot)

        Returns:
            List of artifacts from latest snapshot
        """
        artifacts = await self.get_latest_snapshot(session_id)
        return artifacts[:limit]

    async def get_all_session_artifacts(self, session_id: UUID) -> list[Artifact]:
        """Get ALL artifacts from all tasks in a session.

        Returns artifacts grouped by task, ordered by task creation time
        and then by sequence number within each task.

        Args:
            session_id: Session UUID

        Returns:
            List of all artifacts across all tasks in the session
        """
        stmt = (
            select(Artifact)
            .join(Task, Artifact.task_id == Task.id)
            .where(Task.session_id == session_id)
            .order_by(Task.created_at.asc(), Artifact.sequence_number.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_existing_artifacts_map(
        self, task_id: UUID, artifacts: list[dict[str, Any]]
    ) -> dict[str, Artifact]:
        """Get existing artifacts as a map for batch upsert.

        Queries all existing artifacts that match the given path/filename pairs
        in a single query (avoiding N+1 problem).

        Args:
            task_id: Task UUID
            artifacts: List of artifact data dicts with 'path' and 'filename'

        Returns:
            Dict mapping "path/filename" keys to existing Artifact instances
        """
        if not artifacts:
            return {}

        # Build list of (path, filename) pairs to check
        path_filename_pairs = [
            (artifact_data.get("path", ""), artifact_data["filename"])
            for artifact_data in artifacts
        ]

        # Query all matching artifacts in one query using tuple IN clause
        stmt = (
            select(Artifact)
            .where(Artifact.task_id == task_id)
            .where(tuple_(Artifact.path, Artifact.filename).in_(path_filename_pairs))
        )
        result = await self.session.execute(stmt)
        existing_artifacts = list(result.scalars().all())

        # Build map with path/filename as key
        return {f"{a.path or ''}/{a.filename}": a for a in existing_artifacts}

    async def save_task_snapshot(
        self,
        session_id: UUID,
        task_id: UUID,
        milestone_id: UUID | None,
        artifacts: list[dict[str, Any]],
    ) -> list[Artifact]:
        """Save artifacts for a task milestone with upsert logic.

        Uses batch query to avoid N+1 problem when checking for existing artifacts.
        Each milestone adds to the task's artifacts. If an artifact with
        the same (task_id, path, filename) exists, it's updated.
        Otherwise, a new artifact is created.

        Args:
            session_id: Session UUID
            task_id: Task UUID (snapshot identifier)
            milestone_id: Milestone UUID (optional)
            artifacts: List of artifact data dicts with keys:
                       artifact_type, filename, kind, content, path, sequence_number

        Returns:
            List of created/updated artifacts
        """
        if not artifacts:
            return []

        # Batch query existing artifacts (avoids N+1)
        existing_map = await self._get_existing_artifacts_map(task_id, artifacts)

        result_artifacts: list[Artifact] = []

        for idx, artifact_data in enumerate(artifacts):
            path = artifact_data.get("path", "")
            filename = artifact_data["filename"]
            key = f"{path}/{filename}"

            existing = existing_map.get(key)

            if existing:
                # Update existing artifact
                existing.milestone_id = milestone_id
                existing.artifact_type = artifact_data.get("artifact_type", "code")
                existing.kind = artifact_data["kind"]
                existing.content = artifact_data["content"]
                existing.sequence_number = artifact_data.get("sequence_number", idx)
                result_artifacts.append(existing)
            else:
                # Create new artifact
                artifact = Artifact(
                    session_id=session_id,
                    task_id=task_id,
                    milestone_id=milestone_id,
                    artifact_type=artifact_data.get("artifact_type", "code"),
                    filename=filename,
                    kind=artifact_data["kind"],
                    content=artifact_data["content"],
                    path=path,
                    sequence_number=artifact_data.get("sequence_number", idx),
                )
                self.session.add(artifact)
                result_artifacts.append(artifact)

        await self.session.flush()
        for artifact in result_artifacts:
            await self.session.refresh(artifact)

        return result_artifacts

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

    async def get_code_artifacts(self, session_id: UUID) -> list[Artifact]:
        """Get only code artifacts from latest snapshot.

        Args:
            session_id: Session UUID

        Returns:
            List of code artifacts from latest snapshot
        """
        artifacts = await self.get_latest_snapshot(session_id)
        return [a for a in artifacts if a.artifact_type == "code"]

    async def get_artifact_count(self, session_id: UUID) -> int:
        """Get artifact count from latest snapshot.

        Args:
            session_id: Session UUID

        Returns:
            Number of artifacts in the latest snapshot
        """
        artifacts = await self.get_latest_snapshot(session_id)
        return len(artifacts)

    async def delete_by_paths(self, task_id: UUID, paths: list[str]) -> int:
        """Delete artifacts by their full paths.

        Uses batch delete for efficiency.

        Args:
            task_id: Task UUID
            paths: List of full file paths to delete (e.g., ['src/old.py', 'temp.txt'])

        Returns:
            Number of artifacts deleted
        """
        if not paths:
            return 0

        # Build list of (path, filename) pairs
        path_filename_pairs = []
        for full_path in paths:
            if "/" in full_path:
                path, filename = full_path.rsplit("/", 1)
            else:
                path = ""
                filename = full_path
            path_filename_pairs.append((path, filename))

        # Batch delete using tuple IN clause
        stmt = (
            delete(Artifact)
            .where(Artifact.task_id == task_id)
            .where(tuple_(Artifact.path, Artifact.filename).in_(path_filename_pairs))
        )
        result = await self.session.execute(stmt)
        # CursorResult.rowcount returns number of deleted rows
        return int(getattr(result, "rowcount", 0) or 0)
