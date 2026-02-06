"""Tests for container lifespan context manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bsai.container import ContainerState, lifespan


class TestContainerState:
    """Tests for ContainerState dataclass."""

    def test_container_state_fields(self) -> None:
        """Test ContainerState has all required fields."""
        mock_pm = MagicMock()
        mock_client = MagicMock()
        mock_registry = MagicMock()
        mock_router = MagicMock()
        mock_embedding = MagicMock()

        state = ContainerState(
            prompt_manager=mock_pm,
            llm_client=mock_client,
            model_registry=mock_registry,
            router=mock_router,
            embedding_service=mock_embedding,
        )

        assert state.prompt_manager is mock_pm
        assert state.llm_client is mock_client
        assert state.model_registry is mock_registry
        assert state.router is mock_router
        assert state.embedding_service is mock_embedding


class TestLifespan:
    """Tests for lifespan context manager."""

    @pytest.mark.asyncio
    async def test_lifespan_yields_container_state(self) -> None:
        """Test that lifespan yields a ContainerState."""
        with (
            patch("bsai.container.container.PromptManager") as MockPM,
            patch("bsai.container.container.LiteLLMClient") as MockClient,
            patch("bsai.container.container.ModelRegistry") as MockRegistry,
            patch("bsai.container.container.LLMRouter") as MockRouter,
            patch("bsai.container.container.EmbeddingService") as MockEmbedding,
        ):
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()
            MockRegistry.return_value = mock_registry

            async with lifespan() as container:
                assert isinstance(container, ContainerState)
                assert container.prompt_manager is MockPM.return_value
                assert container.llm_client is MockClient.return_value
                assert container.model_registry is mock_registry
                assert container.router is MockRouter.return_value
                assert container.embedding_service is MockEmbedding.return_value

    @pytest.mark.asyncio
    async def test_lifespan_initializes_model_registry(self) -> None:
        """Test that lifespan initializes the model registry."""
        with (
            patch("bsai.container.container.PromptManager"),
            patch("bsai.container.container.LiteLLMClient"),
            patch("bsai.container.container.ModelRegistry") as MockRegistry,
            patch("bsai.container.container.LLMRouter"),
            patch("bsai.container.container.get_redis"),
            patch("bsai.container.container.SessionCache"),
            patch("bsai.container.container.EmbeddingService"),
        ):
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()
            MockRegistry.return_value = mock_registry

            async with lifespan():
                mock_registry.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_passes_session_to_registry(self) -> None:
        """Test that lifespan passes session to ModelRegistry."""
        mock_session = AsyncMock()

        with (
            patch("bsai.container.container.PromptManager"),
            patch("bsai.container.container.LiteLLMClient"),
            patch("bsai.container.container.ModelRegistry") as MockRegistry,
            patch("bsai.container.container.LLMRouter"),
            patch("bsai.container.container.get_redis"),
            patch("bsai.container.container.SessionCache"),
            patch("bsai.container.container.EmbeddingService"),
        ):
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()
            MockRegistry.return_value = mock_registry

            async with lifespan(mock_session):
                MockRegistry.assert_called_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_lifespan_creates_router_with_registry(self) -> None:
        """Test that lifespan creates LLMRouter with the model registry."""
        with (
            patch("bsai.container.container.PromptManager"),
            patch("bsai.container.container.LiteLLMClient"),
            patch("bsai.container.container.ModelRegistry") as MockRegistry,
            patch("bsai.container.container.LLMRouter") as MockRouter,
            patch("bsai.container.container.get_redis"),
            patch("bsai.container.container.SessionCache"),
            patch("bsai.container.container.EmbeddingService"),
        ):
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()
            MockRegistry.return_value = mock_registry

            async with lifespan():
                MockRouter.assert_called_once_with(mock_registry)

    @pytest.mark.asyncio
    async def test_lifespan_multiple_contexts_independent(self) -> None:
        """Test that multiple lifespan contexts are independent."""
        with (
            patch("bsai.container.container.PromptManager") as MockPM,
            patch("bsai.container.container.LiteLLMClient") as MockClient,
            patch("bsai.container.container.ModelRegistry") as MockRegistry,
            patch("bsai.container.container.LLMRouter"),
            patch("bsai.container.container.get_redis"),
            patch("bsai.container.container.SessionCache"),
            patch("bsai.container.container.EmbeddingService"),
        ):
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()
            MockRegistry.return_value = mock_registry

            async with lifespan():
                pass

            async with lifespan():
                pass

            # Each context should create new instances
            assert MockPM.call_count == 2
            assert MockClient.call_count == 2
            assert MockRegistry.call_count == 2
