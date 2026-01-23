"""Exception handler tests."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from agent.api.exceptions import (
    AccessDeniedError,
    APIError,
    AuthenticationError,
    ConflictError,
    InvalidStateError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
)


def get_detail(error: APIError) -> dict[str, Any]:
    """Helper to safely access error.detail as dict."""
    return cast(dict[str, Any], error.detail)


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

    def test_api_error_with_detail(self) -> None:
        """APIError with detail parameter works correctly."""
        error = APIError(
            message="Something went wrong",
            code="TEST_ERROR",
            status_code=500,
            detail="Additional detail information",
        )
        detail = get_detail(error)
        assert error.message == "Something went wrong"
        assert error.code == "TEST_ERROR"
        assert error.status_code == 500
        assert detail["detail"] == "Additional detail information"

    def test_not_found_error(self) -> None:
        """NotFoundError formats correctly."""
        resource_id = uuid4()
        error = NotFoundError("Session", resource_id)
        detail = get_detail(error)

        assert error.message == "Session not found"
        assert error.code == "NOT_FOUND"
        assert error.status_code == 404
        assert detail["message"] == "Session not found"
        assert str(resource_id) in detail["detail"]

    def test_not_found_error_attributes(self) -> None:
        """NotFoundError stores resource and resource_id attributes."""
        resource_id = uuid4()
        error = NotFoundError("Task", resource_id)

        assert error.resource == "Task"
        assert error.resource_id == resource_id

    def test_authentication_error_default(self) -> None:
        """AuthenticationError with default message."""
        error = AuthenticationError()
        detail = get_detail(error)

        assert error.message == "Not authenticated"
        assert error.code == "AUTHENTICATION_ERROR"
        assert error.status_code == 401
        assert detail["message"] == "Not authenticated"

    def test_authentication_error_custom(self) -> None:
        """AuthenticationError with custom message and detail."""
        error = AuthenticationError(
            message="Token expired",
            detail="Please re-authenticate",
        )
        detail = get_detail(error)

        assert error.message == "Token expired"
        assert error.code == "AUTHENTICATION_ERROR"
        assert error.status_code == 401
        assert detail["detail"] == "Please re-authenticate"

    def test_access_denied_error(self) -> None:
        """AccessDeniedError formats correctly."""
        resource_id = uuid4()
        error = AccessDeniedError("Task", resource_id)
        detail = get_detail(error)

        assert error.message == "Access denied"
        assert error.code == "ACCESS_DENIED"
        assert error.status_code == 403
        assert "Task" in detail["detail"]

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

    def test_invalid_state_error_detail(self) -> None:
        """InvalidStateError includes detail information."""
        error = InvalidStateError(
            resource="Task",
            current_state="completed",
            action="execute",
        )
        detail = get_detail(error)

        assert "Task" in detail["detail"]
        assert "completed" in detail["detail"]
        assert "execute" in detail["detail"]

    def test_validation_error(self) -> None:
        """ValidationError works correctly."""
        error = ValidationError(
            message="Invalid input",
            detail="Field 'email' is required",
        )
        detail = get_detail(error)

        assert error.message == "Invalid input"
        assert error.code == "VALIDATION_ERROR"
        assert error.status_code == 422
        assert detail["detail"] == "Field 'email' is required"

    def test_validation_error_without_detail(self) -> None:
        """ValidationError works without detail."""
        error = ValidationError(message="Invalid format")

        assert error.message == "Invalid format"
        assert error.code == "VALIDATION_ERROR"
        assert error.status_code == 422

    def test_service_unavailable_error(self) -> None:
        """ServiceUnavailableError formats correctly."""
        error = ServiceUnavailableError(service="LLM")

        assert error.message == "LLM service unavailable"
        assert error.code == "SERVICE_UNAVAILABLE"
        assert error.status_code == 503

    def test_service_unavailable_error_with_detail(self) -> None:
        """ServiceUnavailableError with detail."""
        error = ServiceUnavailableError(
            service="Database",
            detail="Connection timeout after 30 seconds",
        )
        detail = get_detail(error)

        assert error.message == "Database service unavailable"
        assert error.code == "SERVICE_UNAVAILABLE"
        assert error.status_code == 503
        assert detail["detail"] == "Connection timeout after 30 seconds"

    def test_rate_limit_error(self) -> None:
        """RateLimitError formats correctly."""
        error = RateLimitError()

        assert error.message == "Rate limit exceeded"
        assert error.code == "RATE_LIMIT_EXCEEDED"
        assert error.status_code == 429

    def test_rate_limit_error_with_detail(self) -> None:
        """RateLimitError with detail."""
        error = RateLimitError(detail="Try again in 60 seconds")
        detail = get_detail(error)

        assert error.message == "Rate limit exceeded"
        assert error.code == "RATE_LIMIT_EXCEEDED"
        assert error.status_code == 429
        assert detail["detail"] == "Try again in 60 seconds"

    def test_conflict_error(self) -> None:
        """ConflictError formats correctly."""
        error = ConflictError(resource="User", identifier="user@example.com")
        detail = get_detail(error)

        assert error.message == "User already exists"
        assert error.code == "CONFLICT"
        assert error.status_code == 409
        assert "user@example.com" in detail["detail"]

    def test_conflict_error_with_custom_detail(self) -> None:
        """ConflictError with custom detail."""
        error = ConflictError(
            resource="Session",
            identifier="abc-123",
            detail="A session with this name already exists in the project",
        )
        detail = get_detail(error)

        assert error.message == "Session already exists"
        assert error.code == "CONFLICT"
        assert error.status_code == 409
        assert detail["detail"] == "A session with this name already exists in the project"
