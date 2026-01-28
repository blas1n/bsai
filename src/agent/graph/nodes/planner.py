"""Planner node for generating execution plans."""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ...logging import get_logger
from ...models.plan import Plan
from ...prompts import get_prompt
from ..state import PlanningAgentState

logger = get_logger(__name__)

PLANNER_SYSTEM_PROMPT = get_prompt("planner")


def create_planner_node(llm: BaseChatModel):
    """Create a planner node that generates structured plans.

    Args:
        llm: LangChain ChatModel

    Returns:
        Planner node function
    """

    def planner_node(state: PlanningAgentState) -> dict:
        """Generate a plan based on user request.

        Args:
            state: Current planning agent state

        Returns:
            Updated state with plan and initialized tracking fields
        """
        # Extract user request from messages
        user_request = None
        for msg in reversed(state["messages"]):
            if msg.type == "human":
                user_request = msg.content
                break

        if not user_request:
            logger.warning("No user request found in messages")
            return {}

        logger.info("Planning started", request=user_request[:100])

        # Generate plan using structured output
        planner_llm = llm.with_structured_output(Plan)

        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=f"Create a plan for: {user_request}"),
        ]

        plan = planner_llm.invoke(messages)

        logger.info(
            "Plan created",
            goal=plan.goal[:50],
            reasoning=plan.reasoning[:100],
            total_steps=plan.total_steps,
        )
        for step in plan.steps:
            logger.debug(
                "Plan step",
                step=step.step_number,
                action=step.action,
                description=step.description[:50],
            )

        return {
            "plan": plan,
            "current_step_index": 0,
            "step_results": {},
            "replans_count": 0,
        }

    return planner_node
