"""Replanner node for adjusting plans based on execution results."""

from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ...logging import get_logger
from ...models.plan import Plan
from ...prompts import get_prompt
from ..state import PlanningAgentState

logger = get_logger(__name__)

REPLANNER_SYSTEM_PROMPT = get_prompt("replanner")
REPLANNER_TEMPLATE = get_prompt("replanner_template")


def create_replanner_node(llm: BaseChatModel):
    """Create a replanner node that adjusts plans.

    Args:
        llm: LangChain ChatModel

    Returns:
        Replanner node function
    """
    replanner_llm = llm.with_structured_output(Plan)

    def replanner_node(state: PlanningAgentState) -> dict:
        """Generate a new plan based on execution progress.

        Args:
            state: Current planning agent state

        Returns:
            Updated state with new plan and reset tracking fields
        """
        plan: Plan | None = state.get("plan")
        if not plan:
            return {}

        replan_count = state.get("replans_count", 0) + 1
        logger.warning(
            "Replanning triggered",
            replan_count=replan_count,
            completed_steps=len(state["step_results"]),
        )

        # Summarize results
        results_summary = "\n".join(
            f"Step {idx + 1}: {result[:300]}"
            for idx, result in sorted(state["step_results"].items())
        )

        replan_prompt = REPLANNER_TEMPLATE.format(
            goal=plan.goal,
            results_summary=results_summary,
            current_step=state["current_step_index"],
            total_steps=plan.total_steps,
        )

        messages = [
            SystemMessage(content=REPLANNER_SYSTEM_PROMPT),
            HumanMessage(content=replan_prompt),
        ]

        new_plan = cast(Plan, replanner_llm.invoke(messages))

        logger.info(
            "New plan created",
            goal=new_plan.goal[:50],
            new_steps=new_plan.total_steps,
        )

        return {
            "plan": new_plan,
            "current_step_index": 0,
            "step_results": {},
            "replans_count": replan_count,
        }

    return replanner_node
