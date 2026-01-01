"""Tests for LLM-related nodes (select_llm, generate_prompt)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import MilestoneStatus
from agent.graph.nodes import generate_prompt_node, select_llm_node
from agent.graph.state import AgentState


class TestSelectLlmNode:
    """Tests for select_llm_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_container: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test successful LLM selection."""
        with patch("agent.graph.nodes.llm.ConductorAgent") as MockConductor:
            mock_conductor = AsyncMock()
            mock_conductor.select_model_for_milestone.return_value = "gpt-4o-mini"
            MockConductor.return_value = mock_conductor

            result = await select_llm_node(state_with_milestone, mock_config, mock_session)

            assert result["milestones"][0]["selected_model"] == "gpt-4o-mini"
            assert result["milestones"][0]["status"] == MilestoneStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_error_handling(
        self,
        mock_container: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test error handling in select_llm."""
        with patch("agent.graph.nodes.llm.ConductorAgent") as MockConductor:
            mock_conductor = AsyncMock()
            mock_conductor.select_model_for_milestone.side_effect = ValueError("Model not found")
            MockConductor.return_value = mock_conductor

            result = await select_llm_node(state_with_milestone, mock_config, mock_session)

            assert result["error"] == "Model not found"
            assert result["error_node"] == "select_llm"


class TestGeneratePromptNode:
    """Tests for generate_prompt_node."""

    @pytest.mark.asyncio
    async def test_success(
        self,
        mock_container: MagicMock,
        mock_config: RunnableConfig,
        mock_session: AsyncMock,
        state_with_milestone: AgentState,
    ) -> None:
        """Test successful prompt generation."""
        with patch("agent.graph.nodes.llm.MetaPrompterAgent") as MockMetaPrompter:
            mock_mp = AsyncMock()
            mock_mp.generate_prompt.return_value = "Optimized prompt for task"
            MockMetaPrompter.return_value = mock_mp

            result = await generate_prompt_node(state_with_milestone, mock_config, mock_session)

            assert result["current_prompt"] == "Optimized prompt for task"
            assert result["milestones"][0]["generated_prompt"] == "Optimized prompt for task"
