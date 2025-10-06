"""
Tracing middleware for OpenTelemetry
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import structlog

logger = structlog.get_logger()


class TracingMiddleware(BaseHTTPMiddleware):
    """Add OpenTelemetry tracing to requests"""

    async def dispatch(self, request: Request, call_next):
        # TODO: Implement OpenTelemetry tracing
        # For now, just log the request
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            request_id=getattr(request.state, "request_id", None),
        )

        response = await call_next(request)

        logger.info(
            "http_response",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            request_id=getattr(request.state, "request_id", None),
        )

        return response
