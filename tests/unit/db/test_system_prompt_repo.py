"""System prompt repository tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.db.repository.system_prompt_repo import SystemPromptRepository

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def prompt_repo(mock_session: AsyncMock) -> SystemPromptRepository:
    """Create system prompt repository."""
    return SystemPromptRepository(mock_session)


class TestGetActivePrompt:
    """Tests for get_active_prompt method."""

    @pytest.mark.asyncio
    async def test_returns_active_prompt(
        self,
        prompt_repo: SystemPromptRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns active prompt for agent type and name."""
        mock_prompt = MagicMock(is_active=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prompt
        mock_session.execute.return_value = mock_result

        result = await prompt_repo.get_active_prompt("conductor", "main")

        assert result is mock_prompt
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_active_prompt(
        self,
        prompt_repo: SystemPromptRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns None when no active prompt exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await prompt_repo.get_active_prompt("conductor", "main")

        assert result is None


class TestGetByNameAndVersion:
    """Tests for get_by_name_and_version method."""

    @pytest.mark.asyncio
    async def test_returns_prompt_by_version(
        self,
        prompt_repo: SystemPromptRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns prompt matching name and version."""
        mock_prompt = MagicMock(name="main", version=2)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prompt
        mock_session.execute.return_value = mock_result

        result = await prompt_repo.get_by_name_and_version("main", 2)

        assert result is not None
        assert result is mock_prompt
        assert result.version == 2

    @pytest.mark.asyncio
    async def test_returns_none_when_version_not_found(
        self,
        prompt_repo: SystemPromptRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns None when version doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await prompt_repo.get_by_name_and_version("main", 999)

        assert result is None


class TestGetAllVersions:
    """Tests for get_all_versions method."""

    @pytest.mark.asyncio
    async def test_returns_all_versions(
        self,
        prompt_repo: SystemPromptRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns all versions of a prompt."""
        mock_prompts = [
            MagicMock(name="main", version=3),
            MagicMock(name="main", version=2),
            MagicMock(name="main", version=1),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_prompts
        mock_session.execute.return_value = mock_result

        result = await prompt_repo.get_all_versions("main")

        assert result == mock_prompts
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_versions(
        self,
        prompt_repo: SystemPromptRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when prompt doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await prompt_repo.get_all_versions("nonexistent")

        assert result == []


class TestGetByAgentType:
    """Tests for get_by_agent_type method."""

    @pytest.mark.asyncio
    async def test_returns_prompts_by_agent_type(
        self,
        prompt_repo: SystemPromptRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns prompts for agent type."""
        mock_prompts = [
            MagicMock(agent_type="conductor", name="main"),
            MagicMock(agent_type="conductor", name="fallback"),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_prompts
        mock_session.execute.return_value = mock_result

        result = await prompt_repo.get_by_agent_type("conductor")

        assert result == mock_prompts

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_unknown_agent_type(
        self,
        prompt_repo: SystemPromptRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list for unknown agent type."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await prompt_repo.get_by_agent_type("unknown")

        assert result == []
