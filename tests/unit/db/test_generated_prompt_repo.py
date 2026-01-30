"""Tests for GeneratedPromptRepository."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.repository.generated_prompt_repo import GeneratedPromptRepository


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repository(mock_session: AsyncMock) -> GeneratedPromptRepository:
    """Create GeneratedPromptRepository instance."""
    return GeneratedPromptRepository(mock_session)


class TestGeneratedPromptRepository:
    """Tests for GeneratedPromptRepository class."""

    def test_init(self, mock_session: AsyncMock) -> None:
        """Test repository initialization."""
        repo = GeneratedPromptRepository(mock_session)
        assert repo.session is mock_session

    async def test_get_by_milestone_found(
        self, repository: GeneratedPromptRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting prompt by milestone when found."""
        milestone_id = uuid4()
        mock_prompt = MagicMock()
        mock_prompt.id = uuid4()
        mock_prompt.milestone_id = milestone_id
        mock_prompt.content = "Generated prompt content"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prompt
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_milestone(milestone_id)

        assert result is mock_prompt
        assert result.milestone_id == milestone_id
        mock_session.execute.assert_called_once()

    async def test_get_by_milestone_not_found(
        self, repository: GeneratedPromptRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting prompt by milestone when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_milestone(uuid4())

        assert result is None

    async def test_get_by_system_prompt(
        self, repository: GeneratedPromptRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting prompts by system prompt ID."""
        system_prompt_id = uuid4()
        mock_prompts = [
            MagicMock(id=uuid4(), system_prompt_id=system_prompt_id, content="Prompt 1"),
            MagicMock(id=uuid4(), system_prompt_id=system_prompt_id, content="Prompt 2"),
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_prompts
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_system_prompt(system_prompt_id, limit=50)

        assert len(result) == 2
        assert result[0].content == "Prompt 1"
        assert result[1].content == "Prompt 2"
        mock_session.execute.assert_called_once()

    async def test_get_by_system_prompt_empty(
        self, repository: GeneratedPromptRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting prompts when none exist."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_system_prompt(uuid4())

        assert result == []

    async def test_get_by_system_prompt_with_custom_limit(
        self, repository: GeneratedPromptRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting prompts with custom limit."""
        mock_prompts = [MagicMock(id=uuid4(), content=f"Prompt {i}") for i in range(10)]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_prompts
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_system_prompt(uuid4(), limit=10)

        assert len(result) == 10
        mock_session.execute.assert_called_once()
