"""Tests for LLM client configuration."""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestCreateLLM:
    """Tests for create_llm function.

    These tests mock the LLM classes to avoid requiring API keys
    and to isolate the routing logic.
    """

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        """Set up mocks for LLM modules before each test."""
        # Create mock modules
        self.mock_anthropic_module = MagicMock()
        self.mock_chat_anthropic = MagicMock()
        self.mock_anthropic_module.ChatAnthropic = self.mock_chat_anthropic

        self.mock_openai_module = MagicMock()
        self.mock_chat_openai = MagicMock()
        self.mock_openai_module.ChatOpenAI = self.mock_chat_openai

        # Patch the modules
        with patch.dict(
            sys.modules,
            {
                "langchain_anthropic": self.mock_anthropic_module,
                "langchain_openai": self.mock_openai_module,
            },
        ):
            # Clear any cached imports
            if "src.agent.llm.client" in sys.modules:
                del sys.modules["src.agent.llm.client"]
            if "src.agent.llm" in sys.modules:
                del sys.modules["src.agent.llm"]

            yield

    def test_create_openai_model_default(self, setup_mocks):
        """Test creating default OpenAI model."""
        from src.agent.llm.client import create_llm

        create_llm()

        self.mock_chat_openai.assert_called_once_with(model="gpt-4o-mini", temperature=0)

    def test_create_openai_model_gpt4(self, setup_mocks):
        """Test creating GPT-4 model."""
        from src.agent.llm.client import create_llm

        create_llm("gpt-4")

        self.mock_chat_openai.assert_called_once_with(model="gpt-4", temperature=0)

    def test_create_anthropic_model_claude(self, setup_mocks):
        """Test creating Claude model."""
        from src.agent.llm.client import create_llm

        create_llm("claude-opus-4-20250514")

        self.mock_chat_anthropic.assert_called_once_with(
            model="claude-opus-4-20250514", temperature=0
        )

    def test_create_anthropic_model_claude_sonnet(self, setup_mocks):
        """Test creating Claude Sonnet model."""
        from src.agent.llm.client import create_llm

        create_llm("claude-sonnet-4-20250514")

        self.mock_chat_anthropic.assert_called_once_with(
            model="claude-sonnet-4-20250514", temperature=0
        )

    def test_non_claude_model_uses_openai(self, setup_mocks):
        """Test that non-Claude models use OpenAI client."""
        from src.agent.llm.client import create_llm

        create_llm("some-other-model")

        self.mock_chat_openai.assert_called_once_with(model="some-other-model", temperature=0)

    def test_claude_prefix_routing(self, setup_mocks):
        """Test that any model starting with 'claude' routes to Anthropic."""
        from src.agent.llm.client import create_llm

        create_llm("claude-custom-model")

        self.mock_chat_anthropic.assert_called_once()
        self.mock_chat_openai.assert_not_called()

    def test_gpt_prefix_routing(self, setup_mocks):
        """Test that GPT models route to OpenAI."""
        from src.agent.llm.client import create_llm

        create_llm("gpt-3.5-turbo")

        self.mock_chat_openai.assert_called_once()
        self.mock_chat_anthropic.assert_not_called()
