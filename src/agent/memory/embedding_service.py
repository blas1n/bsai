"""Embedding service using LiteLLM for vector generation."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import litellm
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    from agent.cache import SessionCache

logger = structlog.get_logger()


class EmbeddingService:
    """Text embedding generation service via LiteLLM.

    Supports caching to avoid redundant API calls for identical text.

    Attributes:
        model: Embedding model name (default: text-embedding-ada-002)
        dimension: Vector dimension (1536 for ada-002)
    """

    # Cache TTL for embeddings (24 hours)
    EMBEDDING_CACHE_TTL = 86400

    def __init__(
        self,
        model: str = "text-embedding-ada-002",
        cache: SessionCache | None = None,
    ) -> None:
        """Initialize embedding service.

        Args:
            model: Embedding model identifier
            cache: Optional session cache for embedding caching
        """
        self.model = model
        self.dimension = 1536  # ada-002 dimension
        self._cache = cache

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Vector embedding as list of floats
        """
        logger.debug("embedding_text_start", text_length=len(text))

        response = await litellm.aembedding(
            model=self.model,
            input=[text],
        )

        embedding: list[float] = response.data[0]["embedding"]

        logger.debug(
            "embedding_text_complete",
            dimension=len(embedding),
        )

        return embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of vector embeddings
        """
        if not texts:
            return []

        logger.info("embedding_batch_start", count=len(texts))

        response = await litellm.aembedding(
            model=self.model,
            input=texts,
        )

        embeddings: list[list[float]] = [item["embedding"] for item in response.data]

        logger.info("embedding_batch_complete", count=len(embeddings))

        return embeddings

    async def embed_with_cache(self, text: str) -> list[float]:
        """Generate embedding with Redis caching.

        Args:
            text: Text to embed

        Returns:
            Vector embedding (from cache or freshly generated)
        """
        if self._cache is None:
            return await self.embed_text(text)

        # Generate cache key from text hash
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        cache_key = f"embedding:{self.model}:{text_hash}"

        # Try cache first
        cached = await self._cache.client.get(cache_key)
        if cached:
            logger.debug("embedding_cache_hit", cache_key=cache_key)
            result: list[float] = json.loads(cached)
            return result

        # Generate and cache
        embedding = await self.embed_text(text)
        await self._cache.client.setex(
            cache_key,
            self.EMBEDDING_CACHE_TTL,
            json.dumps(embedding),
        )

        logger.debug("embedding_cached", cache_key=cache_key)
        return embedding

    async def get_similarity(
        self,
        embedding1: list[float],
        embedding2: list[float],
    ) -> float:
        """Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0.0 to 1.0)
        """
        if len(embedding1) != len(embedding2):
            raise ValueError("Embeddings must have the same dimension")

        dot_product = sum(a * b for a, b in zip(embedding1, embedding2, strict=True))
        norm1 = sum(a * a for a in embedding1) ** 0.5
        norm2 = sum(b * b for b in embedding2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)
