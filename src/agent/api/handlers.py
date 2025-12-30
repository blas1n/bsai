"""Global exception handlers for FastAPI."""

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .exceptions import APIError
from .schemas import ErrorResponse

logger = structlog.get_logger()


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(APIError)
    async def api_error_handler(
        request: Request,
        exc: APIError,
    ) -> JSONResponse:
        """Handle custom API errors.

        Args:
            request: Request instance
            exc: APIError exception

        Returns:
            JSON error response
        """
        request_id = getattr(request.state, "request_id", "unknown")

        logger.warning(
            "api_error",
            request_id=request_id,
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
        )

        # exc.detail is a dict from HTTPException, get the detail string
        detail_str = None
        if isinstance(exc.detail, dict):
            detail_str = exc.detail.get("detail")
        elif isinstance(exc.detail, str):
            detail_str = exc.detail

        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=exc.message,
                detail=detail_str,
                code=exc.code,
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        """Handle HTTP exceptions.

        Args:
            request: Request instance
            exc: HTTPException

        Returns:
            JSON error response
        """
        request_id = getattr(request.state, "request_id", "unknown")

        logger.warning(
            "http_error",
            request_id=request_id,
            status_code=exc.status_code,
            detail=exc.detail,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=str(exc.detail),
                code=f"HTTP_{exc.status_code}",
                request_id=request_id,
            ).model_dump(),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Handle request validation errors.

        Args:
            request: Request instance
            exc: RequestValidationError

        Returns:
            JSON error response with validation details
        """
        request_id = getattr(request.state, "request_id", "unknown")

        # Format validation errors
        errors = []
        for error in exc.errors():
            loc = ".".join(str(x) for x in error["loc"])
            errors.append(f"{loc}: {error['msg']}")

        detail = "; ".join(errors)

        logger.warning(
            "validation_error",
            request_id=request_id,
            errors=exc.errors(),
        )

        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error="Validation error",
                detail=detail,
                code="VALIDATION_ERROR",
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle unhandled exceptions.

        Args:
            request: Request instance
            exc: Unhandled exception

        Returns:
            JSON error response
        """
        request_id = getattr(request.state, "request_id", "unknown")

        logger.exception(
            "unhandled_error",
            request_id=request_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )

        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="Internal server error",
                detail=None,  # Don't expose internal details
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )
