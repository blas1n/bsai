"""Custom exceptions for API layer."""

from typing import Any

from fastapi import HTTPException


class APIError(HTTPException):
    """Base exception for API errors.

    Extends HTTPException for native FastAPI integration.
    """

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 400,
        detail: str | None = None,
    ) -> None:
        """Initialize API error.

        Args:
            message: Error message
            code: Error code
            status_code: HTTP status code
            detail: Additional detail information
        """
        super().__init__(
            status_code=status_code,
            detail={"message": message, "code": code, "detail": detail},
        )
        self.message = message
        self.code = code


class NotFoundError(APIError):
    """Resource not found error."""

    def __init__(
        self,
        resource: str,
        resource_id: Any,
    ) -> None:
        """Initialize not found error.

        Args:
            resource: Resource type (e.g., "Session", "Task")
            resource_id: Resource identifier
        """
        super().__init__(
            message=f"{resource} not found",
            code="NOT_FOUND",
            status_code=404,
            detail=f"{resource} with id '{resource_id}' does not exist",
        )
        self.resource = resource
        self.resource_id = resource_id


class AuthenticationError(APIError):
    """Authentication error."""

    def __init__(
        self,
        message: str = "Not authenticated",
        detail: str | None = None,
    ) -> None:
        """Initialize authentication error.

        Args:
            message: Error message
            detail: Additional detail
        """
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            status_code=401,
            detail=detail,
        )


class AccessDeniedError(APIError):
    """Access denied error."""

    def __init__(
        self,
        resource: str,
        resource_id: Any,
    ) -> None:
        """Initialize access denied error.

        Args:
            resource: Resource type
            resource_id: Resource identifier
        """
        super().__init__(
            message="Access denied",
            code="ACCESS_DENIED",
            status_code=403,
            detail=f"You do not have access to {resource} '{resource_id}'",
        )


class InvalidStateError(APIError):
    """Invalid resource state error."""

    def __init__(
        self,
        resource: str,
        current_state: str,
        action: str,
    ) -> None:
        """Initialize invalid state error.

        Args:
            resource: Resource type
            current_state: Current resource state
            action: Attempted action
        """
        super().__init__(
            message=f"Cannot {action} {resource} in '{current_state}' state",
            code="INVALID_STATE",
            status_code=400,
            detail=f"The {resource} is in '{current_state}' state and cannot be {action}",
        )


class ValidationError(APIError):
    """Validation error."""

    def __init__(
        self,
        message: str,
        detail: str | None = None,
    ) -> None:
        """Initialize validation error.

        Args:
            message: Error message
            detail: Additional detail
        """
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=422,
            detail=detail,
        )


class ServiceUnavailableError(APIError):
    """Service unavailable error."""

    def __init__(
        self,
        service: str,
        detail: str | None = None,
    ) -> None:
        """Initialize service unavailable error.

        Args:
            service: Service name
            detail: Additional detail
        """
        super().__init__(
            message=f"{service} service unavailable",
            code="SERVICE_UNAVAILABLE",
            status_code=503,
            detail=detail,
        )


class RateLimitError(APIError):
    """Rate limit exceeded error."""

    def __init__(
        self,
        detail: str | None = None,
    ) -> None:
        """Initialize rate limit error.

        Args:
            detail: Additional detail
        """
        super().__init__(
            message="Rate limit exceeded",
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            detail=detail,
        )


class ConflictError(APIError):
    """Resource conflict error."""

    def __init__(
        self,
        resource: str,
        identifier: str,
        detail: str | None = None,
    ) -> None:
        """Initialize conflict error.

        Args:
            resource: Resource type
            identifier: Resource identifier causing conflict
            detail: Additional detail
        """
        super().__init__(
            message=f"{resource} already exists",
            code="CONFLICT",
            status_code=409,
            detail=detail or f"{resource} with identifier '{identifier}' already exists",
        )
