"""Executor node for performing plan steps."""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ...logging import get_logger
from ...prompts import get_prompt
from ..state import PlanningAgentState

logger = get_logger(__name__)

EXECUTOR_SYSTEM_PROMPT = get_prompt("executor")
EXECUTOR_TEMPLATE = get_prompt("executor_template")


def create_executor_node(llm: BaseChatModel, tools: list):
    """Create an executor node that performs plan steps.

    Args:
        llm: LangChain ChatModel
        tools: List of tools to bind

    Returns:
        Executor node function
    """
    llm_with_tools = llm.bind_tools(tools)

    def executor_node(state: PlanningAgentState) -> dict:
        """Execute the current step of the plan.

        Args:
            state: Current planning agent state

        Returns:
            Updated state with execution response message
        """
        plan = state.get("plan")
        if not plan:
            return {}

        current_idx = state["current_step_index"]
        if current_idx >= plan.total_steps:
            return {}

        current_step = plan.steps[current_idx]

        logger.info(
            "Executing step",
            step=current_step.step_number,
            total=plan.total_steps,
            action=current_step.action,
            description=current_step.description[:50],
        )

        # Build context from previous results
        previous_context = ""
        if state["step_results"]:
            previous_context = "Previous results:\n"
            for idx, result in sorted(state["step_results"].items()):
                previous_context += f"- Step {idx + 1}: {result[:200]}...\n"

        execution_prompt = EXECUTOR_TEMPLATE.format(
            previous_context=previous_context,
            step_number=current_step.step_number,
            action=current_step.action,
            description=current_step.description,
            input_data=current_step.input_data,
            expected_output=current_step.expected_output,
        )

        messages = [
            SystemMessage(content=EXECUTOR_SYSTEM_PROMPT),
            HumanMessage(content=execution_prompt),
        ]

        response = llm_with_tools.invoke(messages)

        # Log tool calls if any
        if isinstance(response, AIMessage) and response.tool_calls:
            for tool_call in response.tool_calls:
                logger.info(
                    "Tool called",
                    tool=tool_call["name"],
                    args=str(tool_call["args"])[:100],
                )
        else:
            logger.debug("Step completed without tool call")

        return {"messages": [response]}

    return executor_node
