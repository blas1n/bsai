"""Repository for episodic memory operations with vector search."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..models.episodic_memory import EpisodicMemory
from .base import BaseRepository

logger = structlog.get_logger()


class EpisodicMemoryRepository(BaseRepository[EpisodicMemory]):
    """Repository for episodic memory CRUD and vector search.

    Extends BaseRepository with pgvector-specific search operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository.

        Args:
            session: Async database session
        """
        super().__init__(EpisodicMemory, session)

    async def search_by_embedding(
        self,
        embedding: list[float],
        user_id: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
        min_similarity: float = 0.7,
    ) -> list[tuple[EpisodicMemory, float]]:
        """Search memories by vector similarity.

        Uses pgvector cosine distance operator for semantic search.

        Args:
            embedding: Query vector
            user_id: Filter by user
            limit: Maximum results
            memory_types: Optional type filter
            min_similarity: Minimum cosine similarity threshold

        Returns:
            List of (memory, similarity_score) tuples ordered by relevance
        """
        # Calculate similarity as 1 - cosine_distance
        similarity = (1 - EpisodicMemory.embedding.cosine_distance(embedding)).label("similarity")

        stmt = (
            select(EpisodicMemory, similarity)
            .where(EpisodicMemory.user_id == user_id)
            .where(similarity >= min_similarity)
        )

        if memory_types:
            stmt = stmt.where(EpisodicMemory.memory_type.in_(memory_types))

        stmt = stmt.order_by(similarity.desc()).limit(limit)

        result = await self.session.execute(stmt)
        rows = result.all()

        logger.debug(
            "vector_search_complete",
            user_id=user_id,
            results_count=len(rows),
            memory_types=memory_types,
        )

        return [(row[0], float(row[1])) for row in rows]

    async def get_by_user_id(
        self,
        user_id: str,
        memory_types: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EpisodicMemory]:
        """Get memories for a user with optional filtering.

        Args:
            user_id: User identifier
            memory_types: Optional type filter
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of episodic memories
        """
        stmt = (
            select(EpisodicMemory)
            .where(EpisodicMemory.user_id == user_id)
            .order_by(EpisodicMemory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if memory_types:
            stmt = stmt.where(EpisodicMemory.memory_type.in_(memory_types))

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_by_type(
        self,
        user_id: str,
        memory_type: str,
        limit: int = 10,
    ) -> list[EpisodicMemory]:
        """Get recent memories of a specific type.

        Args:
            user_id: User identifier
            memory_type: Memory type to filter
            limit: Maximum results

        Returns:
            List of recent memories
        """
        stmt = (
            select(EpisodicMemory)
            .where(EpisodicMemory.user_id == user_id)
            .where(EpisodicMemory.memory_type == memory_type)
            .order_by(EpisodicMemory.created_at.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_access(self, memory_id: UUID) -> None:
        """Update access count and timestamp.

        Args:
            memory_id: Memory to update
        """
        stmt = (
            update(EpisodicMemory)
            .where(EpisodicMemory.id == memory_id)
            .values(
                access_count=EpisodicMemory.access_count + 1,
                last_accessed_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def bulk_update_importance(
        self,
        memory_ids: list[UUID],
        decay_factor: float,
    ) -> int:
        """Bulk update importance scores with decay.

        Args:
            memory_ids: Memories to update
            decay_factor: Multiplication factor (e.g., 0.95)

        Returns:
            Number of updated records
        """
        if not memory_ids:
            return 0

        stmt = (
            update(EpisodicMemory)
            .where(EpisodicMemory.id.in_(memory_ids))
            .values(importance_score=EpisodicMemory.importance_score * decay_factor)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()

        return result.rowcount  # type: ignore[return-value]

    async def count_by_user(self, user_id: str) -> int:
        """Count total memories for a user.

        Args:
            user_id: User identifier

        Returns:
            Total memory count
        """
        stmt = (
            select(func.count())
            .select_from(EpisodicMemory)
            .where(EpisodicMemory.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar_one()
        return int(count) if count else 0

    async def find_similar_for_consolidation(
        self,
        user_id: str,
        similarity_threshold: float = 0.9,
        limit: int = 100,
    ) -> list[tuple[EpisodicMemory, EpisodicMemory, float]]:
        """Find pairs of similar memories for consolidation.

        Args:
            user_id: User identifier
            similarity_threshold: Minimum similarity for pairs
            limit: Maximum pairs to return

        Returns:
            List of (memory1, memory2, similarity) tuples
        """
        # Self-join to find similar pairs
        m1 = EpisodicMemory
        m2 = aliased(EpisodicMemory)

        similarity = (1 - m1.embedding.cosine_distance(m2.embedding)).label("similarity")

        stmt = (
            select(m1, m2, similarity)
            .where(m1.user_id == user_id)
            .where(m2.user_id == user_id)
            .where(m1.id < m2.id)  # Avoid duplicates
            .where(similarity >= similarity_threshold)
            .order_by(similarity.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return [(row[0], row[1], float(row[2])) for row in result.all()]

    async def get_by_session_id(
        self,
        session_id: UUID,
        limit: int = 100,
    ) -> list[EpisodicMemory]:
        """Get memories for a specific session.

        Args:
            session_id: Session UUID
            limit: Maximum results

        Returns:
            List of episodic memories
        """
        stmt = (
            select(EpisodicMemory)
            .where(EpisodicMemory.session_id == session_id)
            .order_by(EpisodicMemory.created_at.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_task_id(
        self,
        task_id: UUID,
    ) -> list[EpisodicMemory]:
        """Get memories for a specific task.

        Args:
            task_id: Task UUID

        Returns:
            List of episodic memories
        """
        stmt = (
            select(EpisodicMemory)
            .where(EpisodicMemory.task_id == task_id)
            .order_by(EpisodicMemory.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
