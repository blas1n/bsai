"""Tests for container lifespan context manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.container import ContainerState, lifespan


class TestContainerState:
    """Tests for ContainerState dataclass."""

    def test_container_state_immutable(self) -> None:
        """Test that ContainerState is immutable (frozen)."""
        state = ContainerState(
            prompt_manager=MagicMock(),
            llm_client=MagicMock(),
            model_registry=MagicMock(),
            router=MagicMock(),
        )

        with pytest.raises(AttributeError):
            state.prompt_manager = MagicMock()  # type: ignore[misc]

    def test_container_state_fields(self) -> None:
        """Test ContainerState has all required fields."""
        mock_pm = MagicMock()
        mock_client = MagicMock()
        mock_registry = MagicMock()
        mock_router = MagicMock()

        state = ContainerState(
            prompt_manager=mock_pm,
            llm_client=mock_client,
            model_registry=mock_registry,
            router=mock_router,
        )

        assert state.prompt_manager is mock_pm
        assert state.llm_client is mock_client
        assert state.model_registry is mock_registry
        assert state.router is mock_router


class TestLifespan:
    """Tests for lifespan context manager."""

    @pytest.mark.asyncio
    async def test_lifespan_yields_container_state(self) -> None:
        """Test that lifespan yields a ContainerState."""
        with (
            patch("agent.container.container.PromptManager") as MockPM,
            patch("agent.container.container.LiteLLMClient") as MockClient,
            patch("agent.container.container.ModelRegistry") as MockRegistry,
            patch("agent.container.container.LLMRouter") as MockRouter,
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

    @pytest.mark.asyncio
    async def test_lifespan_initializes_model_registry(self) -> None:
        """Test that lifespan initializes the model registry."""
        with (
            patch("agent.container.container.PromptManager"),
            patch("agent.container.container.LiteLLMClient"),
            patch("agent.container.container.ModelRegistry") as MockRegistry,
            patch("agent.container.container.LLMRouter"),
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
            patch("agent.container.container.PromptManager"),
            patch("agent.container.container.LiteLLMClient"),
            patch("agent.container.container.ModelRegistry") as MockRegistry,
            patch("agent.container.container.LLMRouter"),
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
            patch("agent.container.container.PromptManager"),
            patch("agent.container.container.LiteLLMClient"),
            patch("agent.container.container.ModelRegistry") as MockRegistry,
            patch("agent.container.container.LLMRouter") as MockRouter,
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
            patch("agent.container.container.PromptManager") as MockPM,
            patch("agent.container.container.LiteLLMClient") as MockClient,
            patch("agent.container.container.ModelRegistry") as MockRegistry,
            patch("agent.container.container.LLMRouter"),
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
