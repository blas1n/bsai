"""Tests for AgentContainer DI singleton."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.container import AgentContainer, get_container, reset_container


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset container singleton before each test."""
    reset_container()
    yield
    reset_container()


class TestAgentContainer:
    """Tests for AgentContainer singleton."""

    def test_get_instance_returns_singleton(self) -> None:
        """Test that get_instance returns the same instance."""
        instance1 = AgentContainer.get_instance()
        instance2 = AgentContainer.get_instance()

        assert instance1 is instance2

    def test_reset_clears_singleton(self) -> None:
        """Test that reset clears the singleton."""
        instance1 = AgentContainer.get_instance()
        AgentContainer.reset()
        instance2 = AgentContainer.get_instance()

        assert instance1 is not instance2

    def test_not_initialized_by_default(self) -> None:
        """Test container is not initialized by default."""
        container = AgentContainer.get_instance()

        assert container.is_initialized is False

    @pytest.mark.asyncio
    async def test_initialize_sets_flag(self) -> None:
        """Test that initialize sets the initialized flag."""
        container = AgentContainer.get_instance()

        with (
            patch("agent.container.container.PromptManager"),
            patch("agent.container.container.LiteLLMClient"),
            patch("agent.container.container.ModelRegistry") as MockRegistry,
            patch("agent.container.container.LLMRouter"),
        ):
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()
            MockRegistry.return_value = mock_registry

            await container.initialize()

            assert container.is_initialized is True

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self) -> None:
        """Test that calling initialize twice is safe."""
        container = AgentContainer.get_instance()

        with (
            patch("agent.container.container.PromptManager") as MockPM,
            patch("agent.container.container.LiteLLMClient"),
            patch("agent.container.container.ModelRegistry") as MockRegistry,
            patch("agent.container.container.LLMRouter"),
        ):
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()
            MockRegistry.return_value = mock_registry

            await container.initialize()
            await container.initialize()

            # Should only create PromptManager once
            assert MockPM.call_count == 1

    def test_prompt_manager_before_init_raises(self) -> None:
        """Test accessing prompt_manager before init raises."""
        container = AgentContainer.get_instance()

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = container.prompt_manager

    def test_llm_client_before_init_raises(self) -> None:
        """Test accessing llm_client before init raises."""
        container = AgentContainer.get_instance()

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = container.llm_client

    def test_model_registry_before_init_raises(self) -> None:
        """Test accessing model_registry before init raises."""
        container = AgentContainer.get_instance()

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = container.model_registry

    def test_router_before_init_raises(self) -> None:
        """Test accessing router before init raises."""
        container = AgentContainer.get_instance()

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = container.router

    @pytest.mark.asyncio
    async def test_properties_after_init(self) -> None:
        """Test properties work after initialization."""
        container = AgentContainer.get_instance()

        mock_pm = MagicMock()
        mock_client = MagicMock()
        mock_registry = MagicMock()
        mock_registry.initialize = AsyncMock()
        mock_router = MagicMock()

        with (
            patch("agent.container.container.PromptManager", return_value=mock_pm),
            patch("agent.container.container.LiteLLMClient", return_value=mock_client),
            patch("agent.container.container.ModelRegistry", return_value=mock_registry),
            patch("agent.container.container.LLMRouter", return_value=mock_router),
        ):
            await container.initialize()

            assert container.prompt_manager is mock_pm
            assert container.llm_client is mock_client
            assert container.model_registry is mock_registry
            assert container.router is mock_router

    @pytest.mark.asyncio
    async def test_close_resets_initialized(self) -> None:
        """Test that close resets the initialized flag."""
        container = AgentContainer.get_instance()

        with (
            patch("agent.container.container.PromptManager"),
            patch("agent.container.container.LiteLLMClient"),
            patch("agent.container.container.ModelRegistry") as MockRegistry,
            patch("agent.container.container.LLMRouter"),
        ):
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()
            MockRegistry.return_value = mock_registry

            await container.initialize()
            assert container.is_initialized is True

            await container.close()
            assert container.is_initialized is False


class TestGetContainer:
    """Tests for get_container module function."""

    def test_get_container_returns_singleton(self) -> None:
        """Test that get_container returns singleton."""
        container1 = get_container()
        container2 = get_container()

        assert container1 is container2

    def test_get_container_same_as_class(self) -> None:
        """Test that get_container returns same as get_instance."""
        container1 = get_container()
        container2 = AgentContainer.get_instance()

        assert container1 is container2


class TestResetContainer:
    """Tests for reset_container module function."""

    def test_reset_container_works(self) -> None:
        """Test that reset_container clears the global."""
        container1 = get_container()
        reset_container()
        container2 = get_container()

        assert container1 is not container2
