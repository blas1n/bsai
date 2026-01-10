"""Artifact management endpoints."""

import io
import zipfile
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent.db.repository.artifact_repo import ArtifactRepository
from agent.db.repository.task_repo import TaskRepository

from ..dependencies import CurrentUserId, DBSession
from ..exceptions import AccessDeniedError, NotFoundError
from ..schemas import ArtifactResponse, PaginatedResponse

router = APIRouter(prefix="/sessions/{session_id}/tasks/{task_id}/artifacts", tags=["artifacts"])


@router.get(
    "",
    response_model=PaginatedResponse[ArtifactResponse],
    summary="List task artifacts",
)
async def list_artifacts(
    session_id: UUID,
    task_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
    limit: int = 50,
    offset: int = 0,
) -> PaginatedResponse[ArtifactResponse]:
    """List artifacts for a task.

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        db: Database session
        user_id: Current user ID
        limit: Maximum results per page
        offset: Offset for pagination

    Returns:
        Paginated list of artifacts
    """
    # Verify task exists and belongs to user (eagerly load session for user_id check)
    task_repo = TaskRepository(db)
    task = await task_repo.get_with_session(task_id)
    if not task or task.session_id != session_id:
        raise NotFoundError("Task", task_id)
    if task.session.user_id != user_id:
        raise AccessDeniedError("Task", task_id)

    artifact_repo = ArtifactRepository(db)
    artifacts = await artifact_repo.get_by_task_id(task_id)

    # Apply pagination
    total = len(artifacts)
    paginated = artifacts[offset : offset + limit]

    return PaginatedResponse(
        items=[ArtifactResponse.model_validate(a) for a in paginated],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total,
    )


@router.get(
    "/{artifact_id}",
    response_model=ArtifactResponse,
    summary="Get artifact details",
)
async def get_artifact(
    session_id: UUID,
    task_id: UUID,
    artifact_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
) -> ArtifactResponse:
    """Get a specific artifact.

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID (for URL consistency)
        artifact_id: Artifact UUID
        db: Database session
        user_id: Current user ID

    Returns:
        Artifact details
    """
    # Verify task exists and belongs to user (eagerly load session for user_id check)
    task_repo = TaskRepository(db)
    task = await task_repo.get_with_session(task_id)
    if not task or task.session_id != session_id:
        raise NotFoundError("Task", task_id)
    if task.session.user_id != user_id:
        raise AccessDeniedError("Task", task_id)

    artifact_repo = ArtifactRepository(db)
    artifact = await artifact_repo.get_by_id(artifact_id)

    if not artifact or artifact.task_id != task_id:
        raise NotFoundError("Artifact", artifact_id)

    return ArtifactResponse.model_validate(artifact)


@router.get(
    "/download/zip",
    summary="Download all artifacts as ZIP",
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "ZIP file containing all artifacts",
        }
    },
)
async def download_artifacts_zip(
    session_id: UUID,
    task_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
) -> StreamingResponse:
    """Download all task artifacts as a ZIP file.

    Creates a ZIP archive with proper folder structure based on
    artifact paths. Files without paths are placed in the root.

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        db: Database session
        user_id: Current user ID

    Returns:
        ZIP file as streaming response
    """
    # Verify task exists and belongs to user (eagerly load session for user_id check)
    task_repo = TaskRepository(db)
    task = await task_repo.get_with_session(task_id)
    if not task or task.session_id != session_id:
        raise NotFoundError("Task", task_id)
    if task.session.user_id != user_id:
        raise AccessDeniedError("Task", task_id)

    # Get all artifacts for task
    artifact_repo = ArtifactRepository(db)
    artifacts = await artifact_repo.get_by_task_id(task_id)

    if not artifacts:
        raise NotFoundError("Artifacts", task_id)

    # Create ZIP in memory
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        used_paths: set[str] = set()

        for artifact in artifacts:
            if artifact.path:
                file_path = artifact.path.lstrip("/")
                if not file_path.endswith(artifact.filename):
                    file_path = f"{file_path}/{artifact.filename}"
            else:
                file_path = artifact.filename

            # Handle duplicate filenames
            original_path = file_path
            counter = 1
            while file_path in used_paths:
                name, ext = (
                    original_path.rsplit(".", 1) if "." in original_path else (original_path, "")
                )
                file_path = f"{name}_{counter}.{ext}" if ext else f"{name}_{counter}"
                counter += 1

            used_paths.add(file_path)
            zf.writestr(file_path, artifact.content)

    zip_buffer.seek(0)
    zip_filename = f"artifacts_{str(task_id)[:8]}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
        },
    )
