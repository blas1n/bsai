"""FastAPI middleware components."""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to each request.

    Adds a unique request ID to each request for tracing and logging.
    The ID is stored in request.state.request_id and returned in
    the X-Request-ID response header.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and add request ID.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response with X-Request-ID header
        """
        # Get existing request ID from header or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in request state
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging.

    Logs request details and response status with timing information.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and log details.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response
        """
        start_time = time.perf_counter()

        # Get request ID from state (set by RequestIDMiddleware)
        request_id = getattr(request.state, "request_id", "unknown")

        # Log request
        logger.info(
            "request_started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query=str(request.query_params),
        )

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log response
        logger.info(
            "request_completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        # Add timing header
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        return response


class CORSMiddleware:
    """CORS middleware configuration helper.

    Provides default CORS configuration for the API.
    Use with FastAPI's add_middleware:

        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            **cors_config(),
        )
    """

    @staticmethod
    def config(
        origins: list[str] | None = None,
        allow_credentials: bool = True,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get CORS configuration.

        Args:
            origins: Allowed origins (default: ["http://localhost:3000"])
            allow_credentials: Allow credentials (default: True)
            allow_methods: Allowed methods (default: ["*"])
            allow_headers: Allowed headers (default: ["*"])

        Returns:
            CORS configuration dict
        """
        return {
            "allow_origins": origins or ["http://localhost:3000"],
            "allow_credentials": allow_credentials,
            "allow_methods": allow_methods or ["*"],
            "allow_headers": allow_headers or ["*"],
        }
