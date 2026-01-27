"""Tests for LangGraph workflow definition."""

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph

from src.agent.graph.state import AgentState
from src.agent.graph.workflow import (
    SYSTEM_PROMPT,
    create_agent_graph,
    create_agent_node,
)


class TestCreateAgentNode:
    """Tests for create_agent_node function."""

    def test_agent_node_prepends_system_message(self):
        """Test that agent node prepends system message to messages."""
        mock_llm = MagicMock()
        mock_response = AIMessage(content="Response")
        mock_llm.invoke.return_value = mock_response

        agent_node = create_agent_node(mock_llm)
        state: AgentState = {"messages": [HumanMessage(content="Hello")]}

        agent_node(state)

        # Verify invoke was called with system message prepended
        call_args = mock_llm.invoke.call_args[0][0]
        assert isinstance(call_args[0], SystemMessage)
        assert call_args[0].content == SYSTEM_PROMPT
        assert isinstance(call_args[1], HumanMessage)
        assert call_args[1].content == "Hello"

    def test_agent_node_returns_response_in_messages(self):
        """Test that agent node returns response in messages dict."""
        mock_llm = MagicMock()
        mock_response = AIMessage(content="I can help with that!")
        mock_llm.invoke.return_value = mock_response

        agent_node = create_agent_node(mock_llm)
        state: AgentState = {"messages": [HumanMessage(content="Help me")]}

        result = agent_node(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0] == mock_response

    def test_agent_node_preserves_conversation_history(self):
        """Test that agent node preserves full conversation history."""
        mock_llm = MagicMock()
        mock_response = AIMessage(content="Third response")
        mock_llm.invoke.return_value = mock_response

        agent_node = create_agent_node(mock_llm)
        state: AgentState = {
            "messages": [
                HumanMessage(content="First"),
                AIMessage(content="Response 1"),
                HumanMessage(content="Second"),
            ]
        }

        agent_node(state)

        # Verify all messages passed (system + 3 conversation messages)
        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 4
        assert isinstance(call_args[0], SystemMessage)


# Create a simple test tool for use in graph tests
@tool
def dummy_tool(x: str) -> str:
    """A dummy tool for testing."""
    return x


class TestCreateAgentGraph:
    """Tests for create_agent_graph function."""

    def test_create_agent_graph_returns_compiled_graph(self):
        """Test that create_agent_graph returns a CompiledStateGraph."""
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        tools = []

        result = create_agent_graph(mock_llm, tools)

        assert isinstance(result, CompiledStateGraph)

    def test_create_agent_graph_binds_tools(self):
        """Test that create_agent_graph binds tools to LLM."""
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm

        tools = [dummy_tool]

        create_agent_graph(mock_llm, tools)

        mock_llm.bind_tools.assert_called_once_with(tools)

    def test_create_agent_graph_has_required_nodes(self):
        """Test that created graph has agent and tools nodes."""
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        tools = []

        graph = create_agent_graph(mock_llm, tools)

        # Check that the graph has the expected structure
        node_names = list(graph.nodes.keys())
        assert "agent" in node_names
        assert "tools" in node_names

    def test_create_agent_graph_with_tools(self):
        """Test graph creation with actual tools."""
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm

        graph = create_agent_graph(mock_llm, [dummy_tool])

        assert isinstance(graph, CompiledStateGraph)


class TestSystemPrompt:
    """Tests for the system prompt constant."""

    def test_system_prompt_exists(self):
        """Test that SYSTEM_PROMPT is defined."""
        assert SYSTEM_PROMPT is not None
        assert isinstance(SYSTEM_PROMPT, str)

    def test_system_prompt_mentions_capabilities(self):
        """Test that system prompt mentions agent capabilities."""
        assert "read" in SYSTEM_PROMPT.lower()
        assert "write" in SYSTEM_PROMPT.lower()
        assert "file" in SYSTEM_PROMPT.lower()
