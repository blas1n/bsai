"""Tests for CustomLLMModelRepository."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.db.repository.custom_llm_model_repo import CustomLLMModelRepository


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repository(mock_session: AsyncMock) -> CustomLLMModelRepository:
    """Create CustomLLMModelRepository instance."""
    return CustomLLMModelRepository(mock_session)


class TestCustomLLMModelRepository:
    """Tests for CustomLLMModelRepository class."""

    def test_init(self, mock_session: AsyncMock) -> None:
        """Test repository initialization."""
        repo = CustomLLMModelRepository(mock_session)
        assert repo.session is mock_session

    async def test_get_by_name_found(
        self, repository: CustomLLMModelRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting model by name when found."""
        mock_model = MagicMock()
        mock_model.name = "my-model"
        mock_model.provider = "openai"
        mock_model.input_price_per_1k = Decimal("0.001")
        mock_model.output_price_per_1k = Decimal("0.002")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_name("my-model")

        assert result is mock_model
        mock_session.execute.assert_called_once()

    async def test_get_by_name_not_found(
        self, repository: CustomLLMModelRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting model by name when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_name("nonexistent-model")

        assert result is None

    async def test_get_all_active(
        self, repository: CustomLLMModelRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting all active models."""
        mock_model_1 = MagicMock()
        mock_model_1.configure_mock(name="model-1", provider="openai")
        mock_model_2 = MagicMock()
        mock_model_2.configure_mock(name="model-2", provider="anthropic")
        mock_models = [mock_model_1, mock_model_2]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_models
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_all_active()

        assert len(result) == 2
        assert result[0].name == "model-1"
        assert result[1].name == "model-2"
        mock_session.execute.assert_called_once()

    async def test_get_all_active_empty(
        self, repository: CustomLLMModelRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting all active models when none exist."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_all_active()

        assert result == []
