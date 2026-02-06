"""Artifact management endpoints.

Artifacts use task-level snapshot system.
Each task creates a complete snapshot of all artifacts.
"""

import io
import zipfile
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from bsai.db.repository.artifact_repo import ArtifactRepository
from bsai.db.repository.session_repo import SessionRepository

from ..dependencies import CurrentUserId, DBSession
from ..exceptions import AccessDeniedError, NotFoundError
from ..schemas import ArtifactResponse, PaginatedResponse

router = APIRouter(prefix="/sessions/{session_id}/artifacts", tags=["artifacts"])


@router.get(
    "",
    response_model=PaginatedResponse[ArtifactResponse],
    summary="List session artifacts",
)
async def list_artifacts(
    session_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
    task_id: UUID | None = None,
    all_tasks: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> PaginatedResponse[ArtifactResponse]:
    """List artifacts for a session.

    Uses task-level snapshot system:
    - With all_tasks=True: Returns ALL artifacts from all tasks in the session
    - With task_id: Returns that specific task's snapshot (for version history)
    - Without task_id: Returns latest completed task's snapshot (default)

    Args:
        session_id: Session UUID
        db: Database session
        user_id: Current user ID
        task_id: Optional task UUID to get specific snapshot
        all_tasks: If True, return artifacts from ALL tasks in the session
        limit: Maximum results per page
        offset: Offset for pagination

    Returns:
        Paginated list of artifacts
    """
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise NotFoundError("Session", session_id)
    if session.user_id != user_id:
        raise AccessDeniedError("Session", session_id)

    artifact_repo = ArtifactRepository(db)

    # Get artifacts based on parameters
    if task_id:
        # Get specific task's snapshot
        artifacts = await artifact_repo.get_by_task_id(task_id, limit=1000)
    elif all_tasks:
        # Get ALL artifacts from all tasks in the session
        artifacts = await artifact_repo.get_all_session_artifacts(session_id)
    else:
        # Get latest snapshot (current state) - backward compatible default
        artifacts = await artifact_repo.get_latest_snapshot(session_id)

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
    artifact_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
) -> ArtifactResponse:
    """Get a specific artifact by ID.

    Args:
        session_id: Session UUID
        artifact_id: Artifact UUID
        db: Database session
        user_id: Current user ID

    Returns:
        Artifact details
    """
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise NotFoundError("Session", session_id)
    if session.user_id != user_id:
        raise AccessDeniedError("Session", session_id)

    artifact_repo = ArtifactRepository(db)
    artifact = await artifact_repo.get_by_id(artifact_id)

    if not artifact or artifact.session_id != session_id:
        raise NotFoundError("Artifact", artifact_id)

    return ArtifactResponse.model_validate(artifact)


@router.get(
    "/download/zip",
    summary="Download all artifacts as ZIP",
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "ZIP file containing all session artifacts",
        }
    },
)
async def download_artifacts_zip(
    session_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
    task_id: UUID | None = None,
) -> StreamingResponse:
    """Download session artifacts as a ZIP file.

    Creates a ZIP archive with proper folder structure based on
    artifact paths.

    Args:
        session_id: Session UUID
        db: Database session
        user_id: Current user ID
        task_id: Optional task UUID to download specific version

    Returns:
        ZIP file as streaming response
    """
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise NotFoundError("Session", session_id)
    if session.user_id != user_id:
        raise AccessDeniedError("Session", session_id)

    artifact_repo = ArtifactRepository(db)
    if task_id:
        artifacts = await artifact_repo.get_by_task_id(task_id)
    else:
        artifacts = await artifact_repo.get_latest_snapshot(session_id)

    if not artifacts:
        raise NotFoundError("Artifacts", session_id)

    # Get task_id from first artifact for filename
    task_id = artifacts[0].task_id

    # Create ZIP in memory
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for artifact in artifacts:
            # Build file path
            if artifact.path:
                file_path = artifact.path.lstrip("/")
                if not file_path.endswith(artifact.filename):
                    file_path = f"{file_path}/{artifact.filename}"
            else:
                file_path = artifact.filename

            zf.writestr(file_path, artifact.content)

    zip_buffer.seek(0)
    zip_filename = f"artifacts_{str(session_id)[:8]}_{str(task_id)[:8]}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
        },
    )
