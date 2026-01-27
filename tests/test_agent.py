"""Tests for CodeAgent class."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.core.agent import CodeAgent


class TestCodeAgentInit:
    """Tests for CodeAgent initialization."""

    @patch("src.agent.core.agent.create_agent_graph")
    @patch("src.agent.core.agent.create_llm")
    def test_init_creates_llm_with_default_model(
        self, mock_create_llm, mock_create_graph
    ):
        """Test that __init__ creates LLM with default model."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_graph.return_value = MagicMock()

        CodeAgent()

        mock_create_llm.assert_called_once_with("gpt-4o-mini")

    @patch("src.agent.core.agent.create_agent_graph")
    @patch("src.agent.core.agent.create_llm")
    def test_init_creates_llm_with_custom_model(
        self, mock_create_llm, mock_create_graph
    ):
        """Test that __init__ creates LLM with custom model."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_graph.return_value = MagicMock()

        CodeAgent(model="gpt-4o")

        mock_create_llm.assert_called_once_with("gpt-4o")

    @patch("src.agent.core.agent.create_agent_graph")
    @patch("src.agent.core.agent.create_llm")
    def test_init_creates_graph_with_tools(self, mock_create_llm, mock_create_graph):
        """Test that __init__ creates graph with file tools."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_graph.return_value = MagicMock()

        CodeAgent()

        mock_create_graph.assert_called_once()
        call_args = mock_create_graph.call_args
        assert call_args[0][0] == mock_llm
        assert len(call_args[0][1]) == 3  # read_file, write_file, list_directory

    @patch("src.agent.core.agent.create_agent_graph")
    @patch("src.agent.core.agent.create_llm")
    def test_init_stores_llm(self, mock_create_llm, mock_create_graph):
        """Test that __init__ stores the LLM instance."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_graph.return_value = MagicMock()

        result = CodeAgent()

        assert result.llm == mock_llm

    @patch("src.agent.core.agent.create_agent_graph")
    @patch("src.agent.core.agent.create_llm")
    def test_init_stores_graph(self, mock_create_llm, mock_create_graph):
        """Test that __init__ stores the graph instance."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_graph = MagicMock()
        mock_create_graph.return_value = mock_graph

        agent = CodeAgent()

        assert agent.graph == mock_graph


class TestCodeAgentRun:
    """Tests for CodeAgent.run method."""

    @patch("src.agent.core.agent.create_agent_graph")
    @patch("src.agent.core.agent.create_llm")
    def test_run_invokes_graph_with_human_message(
        self, mock_create_llm, mock_create_graph
    ):
        """Test that run invokes graph with HumanMessage."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"messages": [AIMessage(content="Response")]}
        mock_create_graph.return_value = mock_graph

        agent = CodeAgent()
        agent.run("Hello")

        mock_graph.invoke.assert_called_once()
        call_args = mock_graph.invoke.call_args[0][0]
        assert "messages" in call_args
        assert len(call_args["messages"]) == 1
        assert isinstance(call_args["messages"][0], HumanMessage)
        assert call_args["messages"][0].content == "Hello"

    @patch("src.agent.core.agent.create_agent_graph")
    @patch("src.agent.core.agent.create_llm")
    def test_run_returns_last_message_content(self, mock_create_llm, mock_create_graph):
        """Test that run returns the last message content as string."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="Hello"),
                AIMessage(content="Hi there!"),
            ]
        }
        mock_create_graph.return_value = mock_graph

        agent = CodeAgent()
        result = agent.run("Hello")

        assert result == "Hi there!"

    @patch("src.agent.core.agent.create_agent_graph")
    @patch("src.agent.core.agent.create_llm")
    def test_run_handles_single_message_response(
        self, mock_create_llm, mock_create_graph
    ):
        """Test that run handles single message in response."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "messages": [AIMessage(content="Only response")]
        }
        mock_create_graph.return_value = mock_graph

        agent = CodeAgent()
        result = agent.run("Test")

        assert result == "Only response"
