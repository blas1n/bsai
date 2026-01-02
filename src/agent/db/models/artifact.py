"""Artifact model for storing generated code and files."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import INTEGER, TEXT, VARCHAR, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .milestone import Milestone
    from .task import Task


class Artifact(Base):
    """Generated artifact (code, file, document) from Worker output.

    Artifacts are extracted from Worker output and stored separately
    for easy retrieval and display in the frontend.

    Attributes:
        id: Primary key (UUID)
        task_id: Foreign key to tasks table
        milestone_id: Foreign key to milestones table (optional)
        artifact_type: Type of artifact (code, file, document)
        filename: Filename or identifier
        kind: File type/extension (e.g., 'js', 'py', 'html', 'md', 'json')
        content: Full content of the artifact
        path: Optional path within project structure
        sequence_number: Order within task (for multiple artifacts)
        created_at: Creation timestamp
    """

    __tablename__ = "artifacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
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

    # Relationships
    task: Mapped["Task"] = relationship(back_populates="artifacts")
    milestone: Mapped["Milestone | None"] = relationship(back_populates="artifacts")

    def __repr__(self) -> str:
        return f"<Artifact(id={self.id}, filename={self.filename}, type={self.artifact_type})>"

    def to_dict(self) -> dict[str, str | int | None]:
        """Convert artifact to dictionary for API response."""
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "milestone_id": str(self.milestone_id) if self.milestone_id else None,
            "type": self.artifact_type,
            "filename": self.filename,
            "kind": self.kind,
            "content": self.content,
            "path": self.path,
            "sequence_number": self.sequence_number,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
