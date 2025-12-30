"""Middleware tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from agent.api.middleware import CORSMiddleware, LoggingMiddleware, RequestIDMiddleware

if TYPE_CHECKING:
    pass


class TestRequestIDMiddleware:
    """Tests for RequestIDMiddleware."""

    def test_generates_request_id_when_not_provided(self) -> None:
        """Generates a new request ID when not in headers."""
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint(request: Request) -> dict[str, str]:
            return {"request_id": request.state.request_id}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 36  # UUID format

    def test_uses_existing_request_id_from_header(self) -> None:
        """Uses existing request ID from X-Request-ID header."""
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint(request: Request) -> dict[str, str]:
            return {"request_id": request.state.request_id}

        client = TestClient(app)
        custom_id = "custom-request-id-123"
        response = client.get("/test", headers={"X-Request-ID": custom_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id
        assert response.json()["request_id"] == custom_id

    def test_stores_request_id_in_request_state(self) -> None:
        """Request ID is stored in request.state."""
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        captured_request_id = None

        @app.get("/test")
        async def test_endpoint(request: Request) -> dict[str, str]:
            nonlocal captured_request_id
            captured_request_id = request.state.request_id
            return {"ok": "true"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert captured_request_id is not None
        assert captured_request_id == response.headers["X-Request-ID"]


class TestLoggingMiddleware:
    """Tests for LoggingMiddleware."""

    def test_logs_request_and_response(self) -> None:
        """Logs request start and completion."""
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        with patch("agent.api.middleware.logger") as mock_logger:
            client = TestClient(app)
            response = client.get("/test")

            assert response.status_code == 200
            # Should log both request_started and request_completed
            assert mock_logger.info.call_count >= 2

    def test_adds_response_time_header(self) -> None:
        """Adds X-Response-Time header to response."""
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(RequestIDMiddleware)

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert "X-Response-Time" in response.headers
        assert "ms" in response.headers["X-Response-Time"]

    def test_handles_unknown_request_id(self) -> None:
        """Handles case when request ID is not set."""
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
        # Note: RequestIDMiddleware is NOT added

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        with patch("agent.api.middleware.logger") as mock_logger:
            client = TestClient(app)
            response = client.get("/test")

            assert response.status_code == 200
            # Should still work with "unknown" request_id
            mock_logger.info.assert_called()


class TestCORSMiddleware:
    """Tests for CORSMiddleware configuration helper."""

    def test_default_config(self) -> None:
        """Returns default CORS configuration."""
        config = CORSMiddleware.config()

        assert config["allow_origins"] == ["http://localhost:3000"]
        assert config["allow_credentials"] is True
        assert config["allow_methods"] == ["*"]
        assert config["allow_headers"] == ["*"]

    def test_custom_origins(self) -> None:
        """Allows custom origins."""
        origins = ["https://example.com", "https://app.example.com"]
        config = CORSMiddleware.config(origins=origins)

        assert config["allow_origins"] == origins

    def test_custom_credentials(self) -> None:
        """Allows custom credentials setting."""
        config = CORSMiddleware.config(allow_credentials=False)

        assert config["allow_credentials"] is False

    def test_custom_methods(self) -> None:
        """Allows custom methods."""
        methods = ["GET", "POST"]
        config = CORSMiddleware.config(allow_methods=methods)

        assert config["allow_methods"] == methods

    def test_custom_headers(self) -> None:
        """Allows custom headers."""
        headers = ["Content-Type", "Authorization"]
        config = CORSMiddleware.config(allow_headers=headers)

        assert config["allow_headers"] == headers

    def test_all_custom_options(self) -> None:
        """Allows all custom options."""
        config = CORSMiddleware.config(
            origins=["https://custom.com"],
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["X-Custom"],
        )

        assert config["allow_origins"] == ["https://custom.com"]
        assert config["allow_credentials"] is False
        assert config["allow_methods"] == ["GET"]
        assert config["allow_headers"] == ["X-Custom"]
