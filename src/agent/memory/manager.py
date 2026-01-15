"""Long-term memory manager for episodic memory operations."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.db.models.enums import MemoryType
from agent.db.models.episodic_memory import EpisodicMemory
from agent.db.repository.episodic_memory_repo import EpisodicMemoryRepository
from agent.prompts import PromptManager
from agent.prompts.keys import MemoryPrompts

from .embedding_service import EmbeddingService

logger = structlog.get_logger()

# Maximum content length before truncation for summary
MAX_CONTENT_LENGTH = 2000


class LongTermMemoryManager:
    """Manager for long-term episodic memory operations.

    Handles storing, retrieving, and managing memories with
    vector embeddings for semantic search.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        """Initialize memory manager.

        Args:
            session: Database session
            embedding_service: Service for generating embeddings
            prompt_manager: Optional prompt manager for templates
        """
        self._session = session
        self._repo = EpisodicMemoryRepository(session)
        self._embedding_service = embedding_service
        self._prompt_manager = prompt_manager or PromptManager()

    # === Storage Methods ===

    async def store_memory(
        self,
        user_id: str,
        session_id: UUID,
        content: str,
        memory_type: MemoryType,
        task_id: UUID | None = None,
        importance_score: float = 0.5,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EpisodicMemory:
        """Store a new episodic memory.

        Args:
            user_id: Owner user ID
            session_id: Source session
            content: Memory content text
            memory_type: Classification of memory
            task_id: Optional source task
            importance_score: Relevance weight (0.0-1.0)
            tags: Searchable tags
            metadata: Additional structured data

        Returns:
            Created memory instance
        """
        # Generate summary if content is too long
        summary = content
        if len(content) > MAX_CONTENT_LENGTH:
            summary = content[:MAX_CONTENT_LENGTH] + "..."

        # Generate embedding
        embedding = await self._embedding_service.embed_with_cache(content)

        memory = await self._repo.create(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            content=content,
            summary=summary,
            embedding=embedding,
            memory_type=memory_type.value,
            importance_score=importance_score,
            tags=tags,
            metadata_json=metadata,
        )

        logger.info(
            "memory_stored",
            memory_id=str(memory.id),
            memory_type=memory_type.value,
            user_id=user_id,
        )

        return memory

    async def store_task_result(
        self,
        user_id: str,
        session_id: UUID,
        task_id: UUID,
        original_request: str,
        final_result: str,
        milestones_summary: str,
    ) -> EpisodicMemory:
        """Store completed task result as memory.

        Args:
            user_id: Owner user ID
            session_id: Source session
            task_id: Completed task
            original_request: User's original request
            final_result: Task output
            milestones_summary: Summary of milestones

        Returns:
            Created memory
        """
        content = self._prompt_manager.render(
            "memory",
            MemoryPrompts.TASK_RESULT_CONTENT,
            original_request=original_request,
            final_result=final_result,
            milestones_summary=milestones_summary,
        )

        return await self.store_memory(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            content=content,
            memory_type=MemoryType.TASK_RESULT,
            importance_score=0.7,
            tags=["task_complete"],
            metadata={
                "original_request": original_request[:500],
                "has_milestones": bool(milestones_summary),
            },
        )

    async def store_qa_learning(
        self,
        user_id: str,
        session_id: UUID,
        original_output: str,
        qa_feedback: str,
        improved_output: str,
        task_id: UUID | None = None,
    ) -> EpisodicMemory:
        """Store QA feedback learning.

        Args:
            user_id: Owner user ID
            session_id: Source session
            original_output: Initial output before QA
            qa_feedback: QA agent feedback
            improved_output: Output after retry
            task_id: Optional source task

        Returns:
            Created learning memory
        """
        content = self._prompt_manager.render(
            "memory",
            MemoryPrompts.QA_LEARNING_CONTENT,
            qa_feedback=qa_feedback,
        )

        return await self.store_memory(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            content=content,
            memory_type=MemoryType.LEARNING,
            importance_score=0.8,
            tags=["qa_learning", "improvement"],
            metadata={
                "feedback_type": "qa_retry",
                "feedback": qa_feedback[:500],
            },
        )

    async def store_error(
        self,
        user_id: str,
        session_id: UUID,
        error_message: str,
        context: str,
        task_id: UUID | None = None,
    ) -> EpisodicMemory:
        """Store error case for learning.

        Args:
            user_id: Owner user ID
            session_id: Source session
            error_message: Error description
            context: Context when error occurred
            task_id: Optional source task

        Returns:
            Created error memory
        """
        content = self._prompt_manager.render(
            "memory",
            MemoryPrompts.ERROR_CONTENT,
            error_message=error_message,
            error_context=context,
        )

        return await self.store_memory(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            content=content,
            memory_type=MemoryType.ERROR,
            importance_score=0.6,
            tags=["error", "failure_case"],
            metadata={
                "error_message": error_message[:500],
            },
        )

    # === Search Methods ===

    async def search_similar(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_types: list[MemoryType] | None = None,
        min_similarity: float = 0.7,
    ) -> list[tuple[EpisodicMemory, float]]:
        """Search for semantically similar memories.

        Args:
            user_id: User to search for
            query: Search query text
            limit: Maximum results
            memory_types: Optional type filter
            min_similarity: Minimum similarity threshold

        Returns:
            List of (memory, similarity_score) tuples
        """
        # Generate query embedding
        query_embedding = await self._embedding_service.embed_with_cache(query)

        type_values = [t.value for t in memory_types] if memory_types else None

        results = await self._repo.search_by_embedding(
            embedding=query_embedding,
            user_id=user_id,
            limit=limit,
            memory_types=type_values,
            min_similarity=min_similarity,
        )

        # Update access counts for retrieved memories
        for memory, _ in results:
            await self._repo.update_access(memory.id)

        logger.info(
            "memory_search_complete",
            user_id=user_id,
            query_length=len(query),
            results_count=len(results),
        )

        return results

    async def get_relevant_context(
        self,
        user_id: str,
        current_task: str,
        limit: int = 3,
    ) -> str:
        """Get formatted context from relevant memories.

        Args:
            user_id: User identifier
            current_task: Current task description
            limit: Maximum memories to include

        Returns:
            Formatted context string for LLM
        """
        results = await self.search_similar(
            user_id=user_id,
            query=current_task,
            limit=limit,
            memory_types=[MemoryType.TASK_RESULT, MemoryType.LEARNING],
        )

        if not results:
            return ""

        header = self._prompt_manager.render(
            "memory",
            MemoryPrompts.CONTEXT_HEADER,
        )
        context_parts = [header]

        for i, (memory, score) in enumerate(results, 1):
            item = self._prompt_manager.render(
                "memory",
                MemoryPrompts.CONTEXT_MEMORY_ITEM,
                index=i,
                score=score,
                summary=memory.summary,
            )
            context_parts.append(item)

        return "\n".join(context_parts)

    # === Management Methods ===

    async def decay_memories(
        self,
        user_id: str,
        decay_factor: float = 0.95,
        min_importance: float = 0.1,
    ) -> int:
        """Apply importance decay to memories.

        Args:
            user_id: User to process
            decay_factor: Multiplication factor
            min_importance: Minimum importance threshold

        Returns:
            Number of memories updated
        """
        memories = await self._repo.get_by_user_id(user_id, limit=1000)

        to_decay = [m.id for m in memories if m.importance_score > min_importance]

        if not to_decay:
            return 0

        count = await self._repo.bulk_update_importance(to_decay, decay_factor)

        logger.info(
            "memory_decay_applied",
            user_id=user_id,
            memories_decayed=count,
            decay_factor=decay_factor,
        )

        return count

    async def consolidate_memories(
        self,
        user_id: str,
        similarity_threshold: float = 0.9,
    ) -> int:
        """Consolidate highly similar memories.

        Args:
            user_id: User to process
            similarity_threshold: Minimum similarity for consolidation

        Returns:
            Number of memories consolidated (deleted)
        """
        pairs = await self._repo.find_similar_for_consolidation(
            user_id=user_id,
            similarity_threshold=similarity_threshold,
        )

        consolidated = 0
        deleted_ids: set[UUID] = set()

        for m1, m2, _similarity in pairs:
            # Skip if either already deleted
            if m1.id in deleted_ids or m2.id in deleted_ids:
                continue

            # Keep the one with higher importance
            to_keep, to_delete = (
                (m1, m2) if m1.importance_score >= m2.importance_score else (m2, m1)
            )

            # Update importance of kept memory
            await self._repo.update(
                to_keep.id,
                importance_score=min(1.0, to_keep.importance_score + 0.1),
            )

            # Delete the duplicate
            await self._repo.delete(to_delete.id)
            deleted_ids.add(to_delete.id)
            consolidated += 1

        logger.info(
            "memory_consolidation_complete",
            user_id=user_id,
            memories_consolidated=consolidated,
        )

        return consolidated

    async def get_memory_stats(
        self,
        user_id: str,
    ) -> dict[str, Any]:
        """Get memory statistics for a user.

        Args:
            user_id: User identifier

        Returns:
            Dictionary with memory statistics
        """
        memories = await self._repo.get_by_user_id(user_id, limit=10000)

        by_type: dict[str, int] = {}
        total_importance = 0.0

        for memory in memories:
            by_type[memory.memory_type] = by_type.get(memory.memory_type, 0) + 1
            total_importance += memory.importance_score

        avg_importance = total_importance / len(memories) if memories else 0.0

        return {
            "total_memories": len(memories),
            "by_type": by_type,
            "average_importance": avg_importance,
        }
