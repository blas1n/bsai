"""Tests for conditional edge functions."""

from agent.graph.edges import (
    MAX_RETRIES,
    AdvanceRoute,
    QARoute,
    has_error,
    route_advance,
    route_qa_decision,
)
from agent.graph.state import AgentState


class TestRouteQaDecision:
    """Tests for route_qa_decision edge function."""

    def test_pass_decision(self) -> None:
        """Test routing for PASS decision."""
        state: AgentState = {
            "current_qa_decision": "pass",
            "retry_count": 0,
        }

        result = route_qa_decision(state)
        assert result == QARoute.NEXT

    def test_retry_within_limit(self) -> None:
        """Test routing for RETRY within limit."""
        state: AgentState = {
            "current_qa_decision": "retry",
            "retry_count": 1,
        }

        result = route_qa_decision(state)
        assert result == QARoute.RETRY

    def test_retry_at_limit(self) -> None:
        """Test routing when retry count equals max."""
        state: AgentState = {
            "current_qa_decision": "retry",
            "retry_count": MAX_RETRIES,
        }

        result = route_qa_decision(state)
        assert result == QARoute.FAIL

    def test_retry_exceeds_limit(self) -> None:
        """Test routing when retry count exceeds max."""
        state: AgentState = {
            "current_qa_decision": "retry",
            "retry_count": MAX_RETRIES + 1,
        }

        result = route_qa_decision(state)
        assert result == QARoute.FAIL

    def test_explicit_fail(self) -> None:
        """Test routing for explicit FAIL decision."""
        state: AgentState = {
            "current_qa_decision": "fail",
            "retry_count": 0,
        }

        result = route_qa_decision(state)
        assert result == QARoute.FAIL

    def test_default_retry_count(self) -> None:
        """Test that missing retry_count defaults to 0."""
        state: AgentState = {
            "current_qa_decision": "retry",
        }

        result = route_qa_decision(state)
        assert result == QARoute.RETRY

    def test_error_state_returns_fail(self) -> None:
        """Test that error in state returns FAIL."""
        state: AgentState = {
            "error": "Something went wrong",
            "current_qa_decision": "pass",
        }

        result = route_qa_decision(state)
        assert result == QARoute.FAIL

    def test_workflow_complete_returns_fail(self) -> None:
        """Test that workflow_complete returns FAIL."""
        state: AgentState = {
            "workflow_complete": True,
            "current_qa_decision": "pass",
        }

        result = route_qa_decision(state)
        assert result == QARoute.FAIL


class TestRouteAdvance:
    """Tests for route_advance edge function."""

    def test_workflow_complete(self) -> None:
        """Test routing when workflow is complete."""
        state: AgentState = {
            "workflow_complete": True,
            "should_continue": False,
        }

        result = route_advance(state)
        assert result == AdvanceRoute.COMPLETE

    def test_continue_to_next(self) -> None:
        """Test routing to next milestone."""
        state: AgentState = {
            "workflow_complete": False,
            "should_continue": True,
        }

        result = route_advance(state)
        assert result == AdvanceRoute.NEXT_MILESTONE

    def test_retry_milestone(self) -> None:
        """Test routing for retry (should_continue=False but not complete)."""
        state: AgentState = {
            "workflow_complete": False,
            "should_continue": False,
        }

        result = route_advance(state)
        assert result == AdvanceRoute.RETRY_MILESTONE

    def test_defaults(self) -> None:
        """Test default values."""
        state: AgentState = {}

        result = route_advance(state)
        assert result == AdvanceRoute.NEXT_MILESTONE


class TestHasError:
    """Tests for has_error edge function."""

    def test_has_error_true(self) -> None:
        """Test detection of error in state."""
        state: AgentState = {
            "error": "Something went wrong",
            "error_node": "analyze_task",
        }

        result = has_error(state)
        assert result is True

    def test_has_error_false(self) -> None:
        """Test no error in state."""
        state: AgentState = {
            "error": None,
        }

        result = has_error(state)
        assert result is False

    def test_has_error_missing(self) -> None:
        """Test missing error key defaults to False."""
        state: AgentState = {}

        result = has_error(state)
        assert result is False
