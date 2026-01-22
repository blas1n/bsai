"""Artifact model for storing generated code and files."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import INTEGER, TEXT, VARCHAR, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .milestone import Milestone
    from .session import Session
    from .task import Task


class Artifact(Base):
    """Generated artifact (code, file, document) from Worker output.

    Artifacts are managed at TASK level as snapshots.
    Each task creates a complete snapshot of all artifacts at that point.
    The task_id identifies which snapshot the artifact belongs to.

    Attributes:
        id: Primary key (UUID)
        session_id: Foreign key to sessions table (for grouping)
        task_id: Foreign key to tasks table (snapshot identifier)
        milestone_id: Foreign key to milestones table (optional)
        artifact_type: Type of artifact (code, file, document)
        filename: Filename or identifier
        kind: File type/extension (e.g., 'js', 'py', 'html', 'md', 'json')
        content: Full content of the artifact
        path: Optional path within project structure
        sequence_number: Order within task snapshot
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "artifacts"
    __table_args__ = (
        # Index for task-based snapshot queries (no unique constraint)
        Index("ix_artifacts_task_path_filename", "task_id", "path", "filename"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"), index=True)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), index=True, nullable=False)
    milestone_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("milestones.id"), index=True, nullable=True
    )
    artifact_type: Mapped[str] = mapped_column(VARCHAR(20), default="code")
    filename: Mapped[str] = mapped_column(VARCHAR(255))
    kind: Mapped[str] = mapped_column(VARCHAR(50))
    content: Mapped[str] = mapped_column(TEXT)
    path: Mapped[str] = mapped_column(VARCHAR(500))
    sequence_number: Mapped[int] = mapped_column(INTEGER, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Relationships
    session: Mapped[Session] = relationship(back_populates="artifacts")
    task: Mapped[Task | None] = relationship(back_populates="artifacts")
    milestone: Mapped[Milestone | None] = relationship(back_populates="artifacts")

    def __repr__(self) -> str:
        return f"<Artifact(id={self.id}, filename={self.filename}, type={self.artifact_type})>"

    def to_dict(self) -> dict[str, str | int | None]:
        """Convert artifact to dictionary for API response."""
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "task_id": str(self.task_id) if self.task_id else None,
            "milestone_id": str(self.milestone_id) if self.milestone_id else None,
            "type": self.artifact_type,
            "filename": self.filename,
            "kind": self.kind,
            "content": self.content,
            "path": self.path,
            "sequence_number": self.sequence_number,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
