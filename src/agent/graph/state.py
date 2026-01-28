"""Agent state definitions."""

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from ..models.plan import Plan


class AgentState(TypedDict):
    """Minimal agent state for tool-calling agent."""

    messages: Annotated[list[BaseMessage], add_messages]


class PlanningAgentState(TypedDict):
    """Plan-and-Execute agent state."""

    messages: Annotated[list[BaseMessage], add_messages]
    plan: Plan | None
    current_step_index: int
    step_results: dict[int, str]
    replans_count: int
