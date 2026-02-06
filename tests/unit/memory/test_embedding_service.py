"""Unit tests for EmbeddingService."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bsai.memory.embedding_service import EmbeddingService

if TYPE_CHECKING:
    pass


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    @pytest.fixture
    def mock_cache(self) -> MagicMock:
        """Create mock SessionCache."""
        cache = MagicMock()
        cache.client = MagicMock()
        cache.client.get = AsyncMock(return_value=None)
        cache.client.setex = AsyncMock()
        return cache

    @pytest.fixture
    def service(self, mock_cache: MagicMock) -> EmbeddingService:
        """Create EmbeddingService with mock cache."""
        return EmbeddingService(cache=mock_cache)

    @pytest.fixture
    def service_no_cache(self) -> EmbeddingService:
        """Create EmbeddingService without cache."""
        return EmbeddingService()

    @pytest.fixture
    def sample_embedding(self) -> list[float]:
        """Sample embedding vector."""
        return [0.1] * 1536

    @pytest.mark.asyncio
    async def test_embed_text_success(
        self, service_no_cache: EmbeddingService, sample_embedding: list[float]
    ) -> None:
        """Test successful text embedding."""
        with patch("bsai.memory.embedding_service.litellm.aembedding") as mock_embed:
            mock_embed.return_value = MagicMock(data=[{"embedding": sample_embedding}])

            result = await service_no_cache.embed_text("test text")

            assert result == sample_embedding
            mock_embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_batch_success(
        self, service_no_cache: EmbeddingService, sample_embedding: list[float]
    ) -> None:
        """Test successful batch embedding."""
        texts = ["text1", "text2", "text3"]
        with patch("bsai.memory.embedding_service.litellm.aembedding") as mock_embed:
            mock_embed.return_value = MagicMock(
                data=[{"embedding": sample_embedding} for _ in texts]
            )

            result = await service_no_cache.embed_batch(texts)

            assert len(result) == 3
            assert all(emb == sample_embedding for emb in result)

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(self, service_no_cache: EmbeddingService) -> None:
        """Test embedding empty list returns empty."""
        result = await service_no_cache.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_with_cache_hit(
        self,
        service: EmbeddingService,
        mock_cache: MagicMock,
        sample_embedding: list[float],
    ) -> None:
        """Test cache hit returns cached embedding."""
        import json

        mock_cache.client.get = AsyncMock(return_value=json.dumps(sample_embedding))

        result = await service.embed_with_cache("test text")

        assert result == sample_embedding
        mock_cache.client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_with_cache_miss(
        self,
        service: EmbeddingService,
        mock_cache: MagicMock,
        sample_embedding: list[float],
    ) -> None:
        """Test cache miss calls embed_text and caches result."""
        mock_cache.client.get = AsyncMock(return_value=None)

        with patch("bsai.memory.embedding_service.litellm.aembedding") as mock_embed:
            mock_embed.return_value = MagicMock(data=[{"embedding": sample_embedding}])

            result = await service.embed_with_cache("test text")

            assert result == sample_embedding
            mock_cache.client.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_with_cache_no_cache_configured(
        self,
        service_no_cache: EmbeddingService,
        sample_embedding: list[float],
    ) -> None:
        """Test embed_with_cache works when no cache is configured."""
        with patch("bsai.memory.embedding_service.litellm.aembedding") as mock_embed:
            mock_embed.return_value = MagicMock(data=[{"embedding": sample_embedding}])

            result = await service_no_cache.embed_with_cache("test text")

            assert result == sample_embedding

    @pytest.mark.asyncio
    async def test_get_similarity(self, service_no_cache: EmbeddingService) -> None:
        """Test cosine similarity calculation."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        vec3 = [0.0, 1.0, 0.0]

        result1 = await service_no_cache.get_similarity(vec1, vec2)
        result2 = await service_no_cache.get_similarity(vec1, vec3)

        assert result1 == pytest.approx(1.0)
        assert result2 == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_get_similarity_partial(self, service_no_cache: EmbeddingService) -> None:
        """Test cosine similarity with partial overlap."""
        vec1 = [1.0, 1.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]

        # cos(45°) ≈ 0.707
        result = await service_no_cache.get_similarity(vec1, vec2)
        assert 0.7 < result < 0.72

    @pytest.mark.asyncio
    async def test_get_similarity_dimension_mismatch(
        self, service_no_cache: EmbeddingService
    ) -> None:
        """Test similarity raises error for mismatched dimensions."""
        vec1 = [1.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]

        with pytest.raises(ValueError, match="same dimension"):
            await service_no_cache.get_similarity(vec1, vec2)

    @pytest.mark.asyncio
    async def test_get_similarity_zero_vector(self, service_no_cache: EmbeddingService) -> None:
        """Test similarity with zero vector returns 0."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 1.0, 1.0]

        result = await service_no_cache.get_similarity(vec1, vec2)
        assert result == 0.0
