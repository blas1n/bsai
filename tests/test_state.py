"""Tests for agent state definition."""

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.graph.state import AgentState


class TestAgentState:
    """Tests for AgentState TypedDict."""

    def test_agent_state_with_messages(self):
        """Test AgentState can hold messages."""
        state: AgentState = {
            "messages": [
                HumanMessage(content="Hello"),
                AIMessage(content="Hi there!"),
            ]
        }

        assert len(state["messages"]) == 2
        assert state["messages"][0].content == "Hello"
        assert state["messages"][1].content == "Hi there!"

    def test_agent_state_empty_messages(self):
        """Test AgentState with empty messages list."""
        state: AgentState = {"messages": []}

        assert state["messages"] == []

    def test_agent_state_message_types(self):
        """Test AgentState accepts different message types."""
        state: AgentState = {
            "messages": [
                HumanMessage(content="User message"),
                AIMessage(content="AI response"),
            ]
        }

        assert isinstance(state["messages"][0], HumanMessage)
        assert isinstance(state["messages"][1], AIMessage)
