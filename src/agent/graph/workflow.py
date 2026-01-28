"""LangGraph workflow definitions."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from ..logging import get_logger
from ..prompts import get_prompt
from .nodes import create_executor_node, create_planner_node, create_replanner_node
from .state import AgentState, PlanningAgentState

logger = get_logger(__name__)

SYSTEM_PROMPT = get_prompt("system")

MAX_REPLANS = 3


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


def create_agent_graph(llm: BaseChatModel, tools: list[BaseTool]) -> CompiledStateGraph[Any]:
    """Create and compile the simple agent graph.

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


def _route_after_planner(state: PlanningAgentState) -> str:
    """Route after planner node.

    Args:
        state: Current planning agent state

    Returns:
        Next node name: 'executor' or 'end'
    """
    plan = state.get("plan")
    if plan is not None and plan.total_steps > 0:
        return "executor"
    return "end"


def _route_after_executor(state: PlanningAgentState) -> str:
    """Route after executor node.

    Args:
        state: Current planning agent state

    Returns:
        Next node name: 'tools', 'next_step', 'replanner', or 'end'
    """
    last_msg = state["messages"][-1]

    # Check for tool calls
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "tools"

    # Check for errors
    content = str(last_msg.content).lower()
    if "error" in content:
        if state.get("replans_count", 0) < MAX_REPLANS:
            return "replanner"
        return "end"

    # Check if more steps remain
    plan = state.get("plan")
    if plan and state["current_step_index"] < plan.total_steps:
        return "next_step"

    return "end"


def _create_result_processor():
    """Create a node to process tool results and advance step.

    Returns:
        Result processor node function
    """

    def process_result(state: PlanningAgentState) -> dict:
        """Process tool execution result and advance to next step.

        Args:
            state: Current planning agent state

        Returns:
            Updated state with new step_results and incremented step index
        """
        current_idx = state["current_step_index"]
        last_msg = state["messages"][-1]

        result_content = str(last_msg.content)
        logger.info(
            "Step result processed",
            step=current_idx + 1,
            result_preview=result_content[:100],
        )

        new_results = dict(state.get("step_results", {}))
        new_results[current_idx] = result_content

        return {
            "step_results": new_results,
            "current_step_index": current_idx + 1,
        }

    return process_result


def create_planning_agent_graph(
    llm: BaseChatModel, tools: list[BaseTool]
) -> CompiledStateGraph[Any]:
    """Create and compile the plan-and-execute agent graph (Phase 2).

    Args:
        llm: LangChain ChatModel
        tools: List of tools to bind

    Returns:
        Compiled StateGraph
    """
    workflow = StateGraph(PlanningAgentState)

    # Add nodes
    workflow.add_node("planner", create_planner_node(llm))
    workflow.add_node("executor", create_executor_node(llm, tools))
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("process_result", _create_result_processor())
    workflow.add_node("replanner", create_replanner_node(llm))

    # Add edges
    workflow.add_edge(START, "planner")

    workflow.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"executor": "executor", "end": END},
    )

    workflow.add_conditional_edges(
        "executor",
        _route_after_executor,
        {
            "tools": "tools",
            "next_step": "executor",
            "replanner": "replanner",
            "end": END,
        },
    )

    workflow.add_edge("tools", "process_result")
    workflow.add_edge("process_result", "executor")

    workflow.add_conditional_edges(
        "replanner",
        _route_after_planner,
        {"executor": "executor", "end": END},
    )

    return workflow.compile()
