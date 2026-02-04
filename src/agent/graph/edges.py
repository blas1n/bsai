"""Conditional edge functions for LangGraph workflow routing.

These functions determine the next node based on current state.
All functions are pure and synchronous for LangGraph compatibility.
"""

from enum import StrEnum

from agent.db.models.enums import TaskComplexity

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


class PromptRoute(StrEnum):
    """MetaPrompter routing options."""

    GENERATE = "generate_prompt"
    SKIP = "skip_prompt"


class CompressionRoute(StrEnum):
    """Context compression routing options."""

    SUMMARIZE = "summarize"
    SKIP = "skip_summarize"


class AdvanceRoute(StrEnum):
    """Milestone advance routing options."""

    NEXT_MILESTONE = "next_milestone"
    COMPLETE = "complete"
    RETRY_MILESTONE = "retry_milestone"


class RecoveryRoute(StrEnum):
    """Recovery routing options."""

    STRATEGY_RETRY = "strategy_retry"  # Try different strategy
    FAILURE_REPORT = "failure_report"  # Generate failure report


class PlanReviewRoute(StrEnum):
    """Plan review routing options."""

    EXECUTE_WORKER = "execute_worker"  # Plan approved, continue to execution
    ARCHITECT = "architect"  # Revision requested, go back to architect
    END = "__end__"  # Plan rejected or workflow should end


# Maximum retry attempts for QA validation
MAX_RETRIES = 3

# Maximum replan iterations to prevent infinite loops
# Note: This is a fallback default. The actual limit is configured via
# AgentSettings.max_replan_iterations and enforced in replan_node.
MAX_REPLAN_ITERATIONS = 3


def should_use_meta_prompter(state: AgentState) -> PromptRoute:
    """Determine if MetaPrompter should be used.

    MetaPrompter is skipped for TRIVIAL and SIMPLE complexity tasks
    as the overhead of prompt optimization is not worth it for simple tasks.

    Args:
        state: Current workflow state

    Returns:
        PromptRoute.GENERATE if MetaPrompter should run,
        PromptRoute.SKIP to go directly to Worker
    """
    milestones = state.get("milestones")
    idx = state.get("current_milestone_index")

    if milestones is None or idx is None or idx >= len(milestones):
        return PromptRoute.SKIP

    milestone = milestones[idx]
    complexity = milestone["complexity"]

    # Skip for trivial/simple tasks
    if complexity in (TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE):
        return PromptRoute.SKIP

    return PromptRoute.GENERATE


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


def should_compress_context(state: AgentState) -> CompressionRoute:
    """Determine if context compression is needed.

    Checks the needs_compression flag set by check_context_node.

    Args:
        state: Current workflow state

    Returns:
        CompressionRoute.SUMMARIZE if compression needed, CompressionRoute.SKIP otherwise
    """
    if state.get("needs_compression", False):
        return CompressionRoute.SUMMARIZE
    return CompressionRoute.SKIP


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


def route_recovery(state: AgentState) -> RecoveryRoute:
    """Route after recovery node.

    Determines whether to:
    1. Retry with a different strategy (if not yet attempted)
    2. Generate failure report (if strategy retry exhausted)

    Args:
        state: Current workflow state

    Returns:
        RecoveryRoute.STRATEGY_RETRY or RecoveryRoute.FAILURE_REPORT
    """
    # If strategy retry was successful (workflow_complete is False),
    # route back to select_llm for the new strategy
    if not state.get("workflow_complete", False):
        return RecoveryRoute.STRATEGY_RETRY

    # Otherwise, go to failure report
    return RecoveryRoute.FAILURE_REPORT
