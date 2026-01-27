"""LangGraph workflow definition."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .state import AgentState

SYSTEM_PROMPT = """You are a helpful code assistant.
You can read files, write files, and list directories."""


def create_agent_node(llm_with_tools: Runnable[Any, Any]) -> Any:
    """Create the agent node function.

    Args:
        llm_with_tools: LLM with tools bound

    Returns:
        Agent node function
    """

    def agent_node(state: AgentState) -> dict[str, Any]:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    return agent_node


def create_agent_graph(
    llm: BaseChatModel, tools: list[BaseTool]
) -> CompiledStateGraph[Any]:
    """Create and compile the agent graph.

    Args:
        llm: LangChain ChatModel
        tools: List of tools to bind

    Returns:
        Compiled StateGraph
    """
    llm_with_tools = llm.bind_tools(tools)

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", create_agent_node(llm_with_tools))
    workflow.add_node("tools", ToolNode(tools))

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", tools_condition)
    workflow.add_edge("tools", "agent")

    return workflow.compile()
