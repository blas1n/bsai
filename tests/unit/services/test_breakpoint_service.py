"""Tests for BreakpointService."""

from uuid import uuid4

import pytest

from agent.services.breakpoint_service import BreakpointService


class TestBreakpointService:
    """Tests for BreakpointService class."""

    @pytest.fixture
    def service(self) -> BreakpointService:
        """Create a BreakpointService instance."""
        return BreakpointService()

    def test_init_creates_empty_dicts(self, service: BreakpointService) -> None:
        """Test that __init__ creates empty dictionaries."""
        assert service._breakpoint_enabled == {}
        assert service._paused_at == {}

    def test_is_breakpoint_enabled_returns_false_by_default(
        self, service: BreakpointService
    ) -> None:
        """Test is_breakpoint_enabled returns False for unknown task."""
        task_id = uuid4()
        assert service.is_breakpoint_enabled(task_id) is False

    def test_is_breakpoint_enabled_returns_true_when_enabled(
        self, service: BreakpointService
    ) -> None:
        """Test is_breakpoint_enabled returns True after enabling."""
        task_id = uuid4()
        service.set_breakpoint_enabled(task_id, True)
        assert service.is_breakpoint_enabled(task_id) is True

    def test_is_breakpoint_enabled_returns_false_when_disabled(
        self, service: BreakpointService
    ) -> None:
        """Test is_breakpoint_enabled returns False after disabling."""
        task_id = uuid4()
        service.set_breakpoint_enabled(task_id, True)
        service.set_breakpoint_enabled(task_id, False)
        assert service.is_breakpoint_enabled(task_id) is False

    def test_set_breakpoint_enabled_stores_value(self, service: BreakpointService) -> None:
        """Test set_breakpoint_enabled stores the value."""
        task_id = uuid4()
        service.set_breakpoint_enabled(task_id, True)
        assert service._breakpoint_enabled[task_id] is True

        service.set_breakpoint_enabled(task_id, False)
        assert service._breakpoint_enabled[task_id] is False

    def test_is_paused_at_returns_false_by_default(self, service: BreakpointService) -> None:
        """Test is_paused_at returns False for unknown task."""
        task_id = uuid4()
        assert service.is_paused_at(task_id, 0) is False

    def test_is_paused_at_returns_true_when_paused_at_milestone(
        self, service: BreakpointService
    ) -> None:
        """Test is_paused_at returns True when task is paused at milestone."""
        task_id = uuid4()
        service.set_paused_at(task_id, 2)
        assert service.is_paused_at(task_id, 2) is True
        assert service.is_paused_at(task_id, 1) is False
        assert service.is_paused_at(task_id, 3) is False

    def test_set_paused_at_stores_milestone_index(self, service: BreakpointService) -> None:
        """Test set_paused_at stores the milestone index."""
        task_id = uuid4()
        service.set_paused_at(task_id, 5)
        assert service._paused_at[task_id] == 5

    def test_set_paused_at_with_none_clears_paused_state(self, service: BreakpointService) -> None:
        """Test set_paused_at with None clears the paused state."""
        task_id = uuid4()
        service.set_paused_at(task_id, 3)
        assert task_id in service._paused_at

        service.set_paused_at(task_id, None)
        assert task_id not in service._paused_at

    def test_set_paused_at_with_none_handles_unknown_task(self, service: BreakpointService) -> None:
        """Test set_paused_at with None handles unknown task gracefully."""
        task_id = uuid4()
        # Should not raise
        service.set_paused_at(task_id, None)
        assert task_id not in service._paused_at

    def test_clear_paused_at_clears_state(self, service: BreakpointService) -> None:
        """Test clear_paused_at clears the paused state."""
        task_id = uuid4()
        service.set_paused_at(task_id, 2)
        assert service.is_paused_at(task_id, 2) is True

        service.clear_paused_at(task_id)
        assert service.is_paused_at(task_id, 2) is False
        assert task_id not in service._paused_at

    def test_clear_paused_at_handles_unknown_task(self, service: BreakpointService) -> None:
        """Test clear_paused_at handles unknown task gracefully."""
        task_id = uuid4()
        # Should not raise
        service.clear_paused_at(task_id)
        assert task_id not in service._paused_at

    def test_cleanup_task_removes_all_state(self, service: BreakpointService) -> None:
        """Test cleanup_task removes all state for a task."""
        task_id = uuid4()
        service.set_breakpoint_enabled(task_id, True)
        service.set_paused_at(task_id, 1)

        assert task_id in service._breakpoint_enabled
        assert task_id in service._paused_at

        service.cleanup_task(task_id)

        assert task_id not in service._breakpoint_enabled
        assert task_id not in service._paused_at

    def test_cleanup_task_handles_unknown_task(self, service: BreakpointService) -> None:
        """Test cleanup_task handles unknown task gracefully."""
        task_id = uuid4()
        # Should not raise
        service.cleanup_task(task_id)
        assert task_id not in service._breakpoint_enabled
        assert task_id not in service._paused_at

    def test_cleanup_task_only_affects_specified_task(self, service: BreakpointService) -> None:
        """Test cleanup_task only affects the specified task."""
        task_id_1 = uuid4()
        task_id_2 = uuid4()

        service.set_breakpoint_enabled(task_id_1, True)
        service.set_breakpoint_enabled(task_id_2, True)
        service.set_paused_at(task_id_1, 0)
        service.set_paused_at(task_id_2, 1)

        service.cleanup_task(task_id_1)

        assert task_id_1 not in service._breakpoint_enabled
        assert task_id_1 not in service._paused_at
        assert task_id_2 in service._breakpoint_enabled
        assert task_id_2 in service._paused_at

    def test_multiple_tasks_independent_state(self, service: BreakpointService) -> None:
        """Test that multiple tasks have independent state."""
        task_id_1 = uuid4()
        task_id_2 = uuid4()

        service.set_breakpoint_enabled(task_id_1, True)
        service.set_breakpoint_enabled(task_id_2, False)
        service.set_paused_at(task_id_1, 0)
        service.set_paused_at(task_id_2, 5)

        assert service.is_breakpoint_enabled(task_id_1) is True
        assert service.is_breakpoint_enabled(task_id_2) is False
        assert service.is_paused_at(task_id_1, 0) is True
        assert service.is_paused_at(task_id_1, 5) is False
        assert service.is_paused_at(task_id_2, 5) is True
        assert service.is_paused_at(task_id_2, 0) is False

    def test_set_paused_at_overwrites_previous_value(self, service: BreakpointService) -> None:
        """Test set_paused_at overwrites previous milestone index."""
        task_id = uuid4()
        service.set_paused_at(task_id, 0)
        assert service.is_paused_at(task_id, 0) is True

        service.set_paused_at(task_id, 3)
        assert service.is_paused_at(task_id, 0) is False
        assert service.is_paused_at(task_id, 3) is True
