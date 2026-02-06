"""Exception handler tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from bsai.api.exceptions import (
    AccessDeniedError,
    InvalidStateError,
    NotFoundError,
)
from bsai.api.handlers import register_exception_handlers
from bsai.api.middleware import RequestIDMiddleware

if TYPE_CHECKING:
    pass


@pytest.fixture
def app_with_handlers() -> FastAPI:
    """Create FastAPI app with exception handlers registered."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
    return app


class TestAPIErrorHandler:
    """Tests for custom API error handler."""

    def test_handles_not_found_error(self, app_with_handlers: FastAPI) -> None:
        """Handles NotFoundError correctly."""

        @app_with_handlers.get("/test")
        async def test_endpoint() -> None:
            raise NotFoundError("Session", "abc-123")

        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "Session not found"
        assert data["code"] == "NOT_FOUND"
        assert "request_id" in data

    def test_handles_access_denied_error(self, app_with_handlers: FastAPI) -> None:
        """Handles AccessDeniedError correctly."""

        @app_with_handlers.get("/test")
        async def test_endpoint() -> None:
            raise AccessDeniedError("Task", "task-456")

        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "Access denied"
        assert data["code"] == "ACCESS_DENIED"

    def test_handles_invalid_state_error(self, app_with_handlers: FastAPI) -> None:
        """Handles InvalidStateError correctly."""

        @app_with_handlers.get("/test")
        async def test_endpoint() -> None:
            raise InvalidStateError(
                resource="Session",
                current_state="paused",
                action="deleted",
            )

        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        response = client.get("/test")

        # InvalidStateError uses status_code=400
        assert response.status_code == 400
        data = response.json()
        assert "paused" in data["error"]
        assert data["code"] == "INVALID_STATE"


class TestHTTPExceptionHandler:
    """Tests for HTTP exception handler."""

    def test_handles_http_exception(self, app_with_handlers: FastAPI) -> None:
        """Handles HTTPException correctly."""

        @app_with_handlers.get("/test")
        async def test_endpoint() -> None:
            raise HTTPException(status_code=400, detail="Bad request message")

        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Bad request message"
        assert data["code"] == "HTTP_400"
        assert "request_id" in data

    def test_handles_401_unauthorized(self, app_with_handlers: FastAPI) -> None:
        """Handles 401 Unauthorized correctly."""

        @app_with_handlers.get("/test")
        async def test_endpoint() -> None:
            raise HTTPException(status_code=401, detail="Not authenticated")

        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "HTTP_401"

    def test_preserves_exception_headers(self, app_with_handlers: FastAPI) -> None:
        """Preserves custom headers from HTTPException."""

        @app_with_handlers.get("/test")
        async def test_endpoint() -> None:
            raise HTTPException(
                status_code=401,
                detail="Auth required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == "Bearer"


class TestValidationErrorHandler:
    """Tests for request validation error handler."""

    def test_handles_validation_error(self, app_with_handlers: FastAPI) -> None:
        """Handles validation errors correctly."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            name: str
            age: int

        @app_with_handlers.post("/test")
        async def test_endpoint(data: TestModel) -> dict[str, str]:
            return {"name": data.name}

        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        response = client.post("/test", json={"name": 123})  # Invalid: name should be str

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Validation error"
        assert data["code"] == "VALIDATION_ERROR"
        assert "request_id" in data

    def test_formats_multiple_validation_errors(self, app_with_handlers: FastAPI) -> None:
        """Formats multiple validation errors correctly."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            name: str
            age: int
            email: str

        @app_with_handlers.post("/test")
        async def test_endpoint(data: TestModel) -> dict[str, str]:
            return {"name": data.name}

        client = TestClient(app_with_handlers, raise_server_exceptions=False)
        response = client.post("/test", json={})  # Missing all fields

        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "VALIDATION_ERROR"
        # Should contain info about missing fields
        assert data["detail"] is not None


class TestUnhandledExceptionHandler:
    """Tests for unhandled exception handler."""

    def test_handles_unhandled_exception(self, app_with_handlers: FastAPI) -> None:
        """Handles unhandled exceptions correctly."""

        @app_with_handlers.get("/test")
        async def test_endpoint() -> None:
            raise ValueError("Something went wrong")

        with patch("bsai.api.handlers.logger") as mock_logger:
            client = TestClient(app_with_handlers, raise_server_exceptions=False)
            response = client.get("/test")

            assert response.status_code == 500
            data = response.json()
            assert data["error"] == "Internal server error"
            assert data["detail"] is None  # Don't expose internal details
            assert data["code"] == "INTERNAL_ERROR"
            mock_logger.exception.assert_called_once()

    def test_logs_exception_details(self, app_with_handlers: FastAPI) -> None:
        """Logs exception details for debugging."""

        @app_with_handlers.get("/test")
        async def test_endpoint() -> None:
            raise RuntimeError("Critical error")

        with patch("bsai.api.handlers.logger") as mock_logger:
            client = TestClient(app_with_handlers, raise_server_exceptions=False)
            client.get("/test")

            mock_logger.exception.assert_called_once()
            call_kwargs = mock_logger.exception.call_args[1]
            assert call_kwargs["error_type"] == "RuntimeError"
            assert "Critical error" in call_kwargs["error"]
