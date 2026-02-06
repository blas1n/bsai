"""Long-term memory module for semantic search and episodic storage.

Provides services for storing and retrieving memories with vector embeddings,
enabling the agent to learn from past experiences.
"""

from .embedding_service import EmbeddingService
from .helpers import get_memory_context, store_qa_learning, store_task_memory
from .manager import LongTermMemoryManager

__all__ = [
    "EmbeddingService",
    "LongTermMemoryManager",
    "get_memory_context",
    "store_task_memory",
    "store_qa_learning",
]
