"""Conditional edge functions for LangGraph workflow routing.

These functions determine the next node based on current state.
All functions are pure and synchronous for LangGraph compatibility.
"""

from enum import StrEnum

from agent.db.models.enums import TaskComplexity

from .state import AgentState


class QARoute(StrEnum):
    """QA validation routing options."""

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


# Maximum retry attempts for QA validation
MAX_RETRIES = 3


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

    Handles three scenarios:
    1. PASS - Move to next milestone
    2. RETRY - Go back to Worker (if under retry limit)
    3. FAIL - Max retries exceeded, end workflow

    Note: FAIL is only set by qa_agent.py when max retries are exceeded.
    The QA prompt only offers PASS/RETRY to prevent premature failure.

    Args:
        state: Current workflow state

    Returns:
        QARoute.NEXT to proceed, QARoute.RETRY to retry Worker, QARoute.FAIL to end
    """
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
