"""Memory management API endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from agent.db.models.enums import MemoryType
from agent.db.repository.episodic_memory_repo import EpisodicMemoryRepository
from agent.memory import EmbeddingService, LongTermMemoryManager

from ..dependencies import Cache, CurrentUserId, DBSession
from ..schemas import PaginatedResponse
from ..schemas.memory import (
    ConsolidateResult,
    DecayResult,
    MemoryDetailResponse,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryStatsResponse,
)

router = APIRouter(prefix="/memories", tags=["memories"])
logger = structlog.get_logger()


def _get_memory_manager(
    db: DBSession,
    cache: Cache,
) -> LongTermMemoryManager:
    """Create memory manager instance.

    Args:
        db: Database session
        cache: Session cache

    Returns:
        LongTermMemoryManager instance
    """
    embedding_service = EmbeddingService(cache=cache)
    return LongTermMemoryManager(
        session=db,
        embedding_service=embedding_service,
    )


@router.post(
    "/search",
    response_model=list[MemorySearchResult],
    summary="Search memories semantically",
)
async def search_memories(
    request: MemorySearchRequest,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> list[MemorySearchResult]:
    """Search user memories by semantic similarity.

    Args:
        request: Search parameters
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        List of matching memories with similarity scores
    """
    manager = _get_memory_manager(db, cache)

    memory_types = None
    if request.memory_types:
        try:
            memory_types = [MemoryType(t) for t in request.memory_types]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid memory type: {e}",
            ) from e

    results = await manager.search_similar(
        user_id=user_id,
        query=request.query,
        limit=request.limit,
        memory_types=memory_types,
        min_similarity=request.min_similarity,
    )

    return [
        MemorySearchResult(
            memory=MemoryResponse(
                id=memory.id,
                user_id=memory.user_id,
                session_id=memory.session_id,
                task_id=memory.task_id,
                summary=memory.summary,
                memory_type=memory.memory_type,
                importance_score=memory.importance_score,
                access_count=memory.access_count,
                tags=memory.tags,
                created_at=memory.created_at,
                last_accessed_at=memory.last_accessed_at,
            ),
            similarity=score,
        )
        for memory, score in results
    ]


@router.get(
    "",
    response_model=PaginatedResponse[MemoryResponse],
    summary="List user memories",
)
async def list_memories(
    db: DBSession,
    user_id: CurrentUserId,
    memory_type: str | None = Query(None, description="Filter by memory type"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> PaginatedResponse[MemoryResponse]:
    """List memories for the authenticated user.

    Args:
        db: Database session
        user_id: Current user ID
        memory_type: Optional type filter
        limit: Maximum results per page
        offset: Pagination offset

    Returns:
        Paginated list of memories
    """
    repo = EpisodicMemoryRepository(db)

    memory_types = [memory_type] if memory_type else None
    memories = await repo.get_by_user_id(
        user_id=user_id,
        memory_types=memory_types,
        limit=limit,
        offset=offset,
    )

    total = await repo.count_by_user(user_id)

    items = [
        MemoryResponse(
            id=m.id,
            user_id=m.user_id,
            session_id=m.session_id,
            task_id=m.task_id,
            summary=m.summary,
            memory_type=m.memory_type,
            importance_score=m.importance_score,
            access_count=m.access_count,
            tags=m.tags,
            created_at=m.created_at,
            last_accessed_at=m.last_accessed_at,
        )
        for m in memories
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(items)) < total,
    )


@router.get(
    "/stats",
    response_model=MemoryStatsResponse,
    summary="Get memory statistics",
)
async def get_memory_stats(
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> MemoryStatsResponse:
    """Get memory statistics for the user.

    Args:
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Memory statistics
    """
    manager = _get_memory_manager(db, cache)
    stats = await manager.get_memory_stats(user_id)

    return MemoryStatsResponse(
        total_memories=stats["total_memories"],
        by_type=stats["by_type"],
        average_importance=stats["average_importance"],
    )


@router.get(
    "/{memory_id}",
    response_model=MemoryDetailResponse,
    summary="Get memory by ID",
)
async def get_memory(
    memory_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
) -> MemoryDetailResponse:
    """Get a specific memory with full details.

    Args:
        memory_id: Memory UUID
        db: Database session
        user_id: Current user ID

    Returns:
        Memory details
    """
    repo = EpisodicMemoryRepository(db)
    memory = await repo.get_by_id(memory_id)

    if memory is None or memory.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    return MemoryDetailResponse(
        id=memory.id,
        user_id=memory.user_id,
        session_id=memory.session_id,
        task_id=memory.task_id,
        summary=memory.summary,
        content=memory.content,
        memory_type=memory.memory_type,
        importance_score=memory.importance_score,
        access_count=memory.access_count,
        tags=memory.tags,
        metadata_json=memory.metadata_json,
        created_at=memory.created_at,
        last_accessed_at=memory.last_accessed_at,
    )


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete memory",
)
async def delete_memory(
    memory_id: UUID,
    db: DBSession,
    user_id: CurrentUserId,
) -> None:
    """Delete a memory.

    Args:
        memory_id: Memory UUID
        db: Database session
        user_id: Current user ID
    """
    repo = EpisodicMemoryRepository(db)
    memory = await repo.get_by_id(memory_id)

    if memory is None or memory.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    await repo.delete(memory_id)

    logger.info("memory_deleted", memory_id=str(memory_id), user_id=user_id)


@router.post(
    "/consolidate",
    response_model=ConsolidateResult,
    summary="Consolidate similar memories",
)
async def consolidate_memories(
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> ConsolidateResult:
    """Consolidate highly similar memories.

    Merges duplicate memories to reduce redundancy and improve search quality.

    Args:
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Consolidation result
    """
    manager = _get_memory_manager(db, cache)

    consolidated_count = await manager.consolidate_memories(user_id=user_id)

    repo = EpisodicMemoryRepository(db)
    remaining_count = await repo.count_by_user(user_id)

    return ConsolidateResult(
        consolidated_count=consolidated_count,
        remaining_count=remaining_count,
    )


@router.post(
    "/decay",
    response_model=DecayResult,
    summary="Apply importance decay",
)
async def decay_memories(
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> DecayResult:
    """Apply importance decay to memories.

    Reduces importance scores over time to prioritize recent memories.

    Args:
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Number of memories affected
    """
    manager = _get_memory_manager(db, cache)

    decayed_count = await manager.decay_memories(user_id=user_id)

    return DecayResult(decayed_count=decayed_count)
