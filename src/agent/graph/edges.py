"""Conditional edge functions for LangGraph workflow routing.

These functions determine the next node based on current state.
All functions are pure and synchronous for LangGraph compatibility.

Simplified 7-node workflow:
    architect -> plan_review -> execute_worker -> verify_qa
        -> execution_breakpoint -> advance -> generate_response -> END
"""

from enum import StrEnum

from .state import AgentState


class QARoute(StrEnum):
    """QA validation routing options.

    Simplified workflow routes:
    - NEXT: Proceed to execution_breakpoint
    - RETRY: Retry current task (via advance node)
    - FAIL: Task failed, go to generate_response
    """

    RETRY = "retry"
    FAIL = "fail"
    NEXT = "next"


class AdvanceRoute(StrEnum):
    """Milestone advance routing options."""

    NEXT_MILESTONE = "next_milestone"
    COMPLETE = "complete"
    RETRY_MILESTONE = "retry_milestone"


class PlanReviewRoute(StrEnum):
    """Plan review routing options."""

    EXECUTE_WORKER = "execute_worker"  # Plan approved, continue to execution
    ARCHITECT = "architect"  # Revision requested, go back to architect
    END = "__end__"  # Plan rejected or workflow should end


# Maximum retry attempts for QA validation
MAX_RETRIES = 3


def route_qa_decision(state: AgentState) -> QARoute:
    """Route based on QA decision.

    Simplified 3-scenario routing:
    1. PASS - Move to execution_breakpoint
    2. RETRY - Go back to Worker via advance (if under retry limit)
    3. FAIL - Max retries exceeded, error, or workflow complete

    Note: FAIL is only set by qa_agent.py when max retries are exceeded.
    The QA prompt only offers PASS/RETRY to prevent premature failure.

    Args:
        state: Current workflow state

    Returns:
        QARoute.NEXT to proceed, QARoute.RETRY to retry Worker,
        QARoute.FAIL to go to generate_response with error
    """
    # Check for errors or early termination first
    if state.get("error") or state.get("workflow_complete"):
        return QARoute.FAIL

    decision = state.get("current_qa_decision")
    retry_count = state.get("retry_count", 0)

    if decision == "pass":
        return QARoute.NEXT
    elif decision == "fail":
        return QARoute.FAIL
    elif decision == "retry" and retry_count < MAX_RETRIES:
        return QARoute.RETRY
    else:
        return QARoute.FAIL


def route_advance(state: AgentState) -> AdvanceRoute:
    """Route after advance node.

    Determines next action after advancing:
    1. complete - All milestones done or task failed
    2. next_milestone - Continue to next milestone
    3. retry_milestone - Retry current milestone (QA retry)

    Args:
        state: Current workflow state

    Returns:
        Routing decision for next step
    """
    if state.get("workflow_complete", False):
        return AdvanceRoute.COMPLETE

    if state.get("should_continue", True):
        return AdvanceRoute.NEXT_MILESTONE

    # Retry case - go back to worker
    return AdvanceRoute.RETRY_MILESTONE


def has_error(state: AgentState) -> bool:
    """Check if workflow has encountered an error.

    Used for conditional routing to error handling.

    Args:
        state: Current workflow state

    Returns:
        True if error exists in state
    """
    return state.get("error") is not None
