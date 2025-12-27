"""Tests for conditional edge functions."""

from uuid import uuid4

from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.edges import (
    MAX_RETRIES,
    AdvanceRoute,
    CompressionRoute,
    PromptRoute,
    QARoute,
    has_error,
    route_advance,
    route_qa_decision,
    should_compress_context,
    should_use_meta_prompter,
)
from agent.graph.state import AgentState, MilestoneData


def create_milestone(complexity: TaskComplexity) -> MilestoneData:
    """Helper to create a milestone with given complexity."""
    return MilestoneData(
        id=uuid4(),
        description="Test milestone",
        complexity=complexity,
        acceptance_criteria="Done",
        status=MilestoneStatus.PENDING,
        selected_model=None,
        generated_prompt=None,
        worker_output=None,
        qa_feedback=None,
        retry_count=0,
    )


class TestShouldUseMetaPrompter:
    """Tests for should_use_meta_prompter edge function."""

    def test_skip_for_trivial(self) -> None:
        """Test MetaPrompter is skipped for TRIVIAL complexity."""
        state: AgentState = {
            "milestones": [create_milestone(TaskComplexity.TRIVIAL)],
            "current_milestone_index": 0,
        }

        result = should_use_meta_prompter(state)
        assert result == PromptRoute.SKIP

    def test_skip_for_simple(self) -> None:
        """Test MetaPrompter is skipped for SIMPLE complexity."""
        state: AgentState = {
            "milestones": [create_milestone(TaskComplexity.SIMPLE)],
            "current_milestone_index": 0,
        }

        result = should_use_meta_prompter(state)
        assert result == PromptRoute.SKIP

    def test_generate_for_moderate(self) -> None:
        """Test MetaPrompter is used for MODERATE complexity."""
        state: AgentState = {
            "milestones": [create_milestone(TaskComplexity.MODERATE)],
            "current_milestone_index": 0,
        }

        result = should_use_meta_prompter(state)
        assert result == PromptRoute.GENERATE

    def test_generate_for_complex(self) -> None:
        """Test MetaPrompter is used for COMPLEX complexity."""
        state: AgentState = {
            "milestones": [create_milestone(TaskComplexity.COMPLEX)],
            "current_milestone_index": 0,
        }

        result = should_use_meta_prompter(state)
        assert result == PromptRoute.GENERATE

    def test_generate_for_context_heavy(self) -> None:
        """Test MetaPrompter is used for CONTEXT_HEAVY complexity."""
        state: AgentState = {
            "milestones": [create_milestone(TaskComplexity.CONTEXT_HEAVY)],
            "current_milestone_index": 0,
        }

        result = should_use_meta_prompter(state)
        assert result == PromptRoute.GENERATE

    def test_uses_current_milestone_index(self) -> None:
        """Test that current_milestone_index is used correctly."""
        state: AgentState = {
            "milestones": [
                create_milestone(TaskComplexity.TRIVIAL),  # index 0
                create_milestone(TaskComplexity.COMPLEX),  # index 1
            ],
            "current_milestone_index": 1,
        }

        result = should_use_meta_prompter(state)
        assert result == PromptRoute.GENERATE


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


class TestShouldCompressContext:
    """Tests for should_compress_context edge function."""

    def test_needs_compression_true(self) -> None:
        """Test routing when compression is needed."""
        state: AgentState = {
            "needs_compression": True,
        }

        result = should_compress_context(state)
        assert result == CompressionRoute.SUMMARIZE

    def test_needs_compression_false(self) -> None:
        """Test routing when compression is not needed."""
        state: AgentState = {
            "needs_compression": False,
        }

        result = should_compress_context(state)
        assert result == CompressionRoute.SKIP

    def test_default_no_compression(self) -> None:
        """Test that missing needs_compression defaults to False."""
        state: AgentState = {}

        result = should_compress_context(state)
        assert result == CompressionRoute.SKIP


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
