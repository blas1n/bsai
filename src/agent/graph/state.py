"""Agent state definition."""

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Minimal agent state for tool-calling agent."""

    messages: Annotated[list[BaseMessage], add_messages]
