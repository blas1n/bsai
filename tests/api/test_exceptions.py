"""Exception handler tests."""

from __future__ import annotations

from uuid import uuid4

from agent.api.exceptions import (
    AccessDeniedError,
    APIError,
    InvalidStateError,
    NotFoundError,
    ValidationError,
)


class TestAPIExceptions:
    """API exception tests."""

    def test_api_error_base(self) -> None:
        """APIError base class works correctly."""
        error = APIError(
            message="Something went wrong",
            code="TEST_ERROR",
            status_code=500,
        )
        assert error.message == "Something went wrong"
        assert error.code == "TEST_ERROR"
        assert error.status_code == 500

    def test_not_found_error(self) -> None:
        """NotFoundError formats correctly."""
        resource_id = uuid4()
        error = NotFoundError("Session", resource_id)

        assert error.message == "Session not found"
        assert error.code == "NOT_FOUND"
        assert error.status_code == 404
        assert error.detail["message"] == "Session not found"
        assert str(resource_id) in error.detail["detail"]

    def test_access_denied_error(self) -> None:
        """AccessDeniedError formats correctly."""
        resource_id = uuid4()
        error = AccessDeniedError("Task", resource_id)

        assert error.message == "Access denied"
        assert error.code == "ACCESS_DENIED"
        assert error.status_code == 403
        assert "Task" in error.detail["detail"]

    def test_invalid_state_error(self) -> None:
        """InvalidStateError formats correctly."""
        error = InvalidStateError(
            resource="Session",
            current_state="paused",
            action="pause",
        )

        assert "Session" in error.message
        assert "paused" in error.message
        assert "pause" in error.message
        assert error.code == "INVALID_STATE"
        assert error.status_code == 400

    def test_validation_error(self) -> None:
        """ValidationError works correctly."""
        error = ValidationError(
            message="Invalid input",
            detail={"field": ["error1", "error2"]},
        )

        assert error.message == "Invalid input"
        assert error.code == "VALIDATION_ERROR"
        assert error.status_code == 422
        assert error.detail["detail"] == {"field": ["error1", "error2"]}
