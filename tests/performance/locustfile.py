"""Locust load testing configuration for BSAI API.

Run with:
    locust -f tests/performance/locustfile.py --host=http://localhost:8000
"""

import random
import string
from uuid import uuid4

from locust import HttpUser, between, task


def random_string(length: int = 10) -> str:
    """Generate a random string."""
    return "".join(random.choices(string.ascii_letters, k=length))


class BSAIUser(HttpUser):
    """Simulates a BSAI API user."""

    wait_time = between(1, 3)

    def on_start(self):
        """Called when a simulated user starts."""
        self.session_id = None
        self.task_id = None
        self.user_id = f"load-test-user-{random_string(8)}"

    @task(10)
    def health_check(self):
        """Test health endpoint - most frequent."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(5)
    def create_session(self):
        """Test session creation."""
        headers = {
            "Content-Type": "application/json",
            "X-User-ID": self.user_id,  # Simulated auth header
        }

        with self.client.post(
            "/api/v1/sessions",
            json={},
            headers=headers,
            catch_response=True,
            name="/api/v1/sessions [POST]",
        ) as response:
            if response.status_code == 201:
                data = response.json()
                self.session_id = data.get("id")
                response.success()
            elif response.status_code == 401:
                # Expected without auth
                response.success()
            else:
                response.failure(f"Session creation failed: {response.status_code}")

    @task(8)
    def list_sessions(self):
        """Test listing sessions."""
        headers = {"X-User-ID": self.user_id}

        with self.client.get(
            "/api/v1/sessions",
            headers=headers,
            catch_response=True,
            name="/api/v1/sessions [GET]",
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"List sessions failed: {response.status_code}")

    @task(3)
    def get_session_detail(self):
        """Test getting session detail."""
        if not self.session_id:
            return

        headers = {"X-User-ID": self.user_id}

        with self.client.get(
            f"/api/v1/sessions/{self.session_id}",
            headers=headers,
            catch_response=True,
            name="/api/v1/sessions/{id} [GET]",
        ) as response:
            if response.status_code in [200, 401, 404]:
                response.success()
            else:
                response.failure(f"Get session failed: {response.status_code}")

    @task(2)
    def create_task(self):
        """Test task creation."""
        if not self.session_id:
            return

        headers = {
            "Content-Type": "application/json",
            "X-User-ID": self.user_id,
        }

        task_request = {
            "original_request": f"Test task: {random_string(20)}",
        }

        with self.client.post(
            f"/api/v1/sessions/{self.session_id}/tasks",
            json=task_request,
            headers=headers,
            catch_response=True,
            name="/api/v1/sessions/{id}/tasks [POST]",
        ) as response:
            if response.status_code == 202:
                data = response.json()
                self.task_id = data.get("id")
                response.success()
            elif response.status_code in [401, 404]:
                response.success()
            else:
                response.failure(f"Task creation failed: {response.status_code}")

    @task(4)
    def list_tasks(self):
        """Test listing tasks for a session."""
        if not self.session_id:
            return

        headers = {"X-User-ID": self.user_id}

        with self.client.get(
            f"/api/v1/sessions/{self.session_id}/tasks",
            headers=headers,
            catch_response=True,
            name="/api/v1/sessions/{id}/tasks [GET]",
        ) as response:
            if response.status_code in [200, 401, 404]:
                response.success()
            else:
                response.failure(f"List tasks failed: {response.status_code}")

    @task(2)
    def get_task_detail(self):
        """Test getting task detail."""
        if not self.session_id or not self.task_id:
            return

        headers = {"X-User-ID": self.user_id}

        with self.client.get(
            f"/api/v1/sessions/{self.session_id}/tasks/{self.task_id}",
            headers=headers,
            catch_response=True,
            name="/api/v1/sessions/{id}/tasks/{task_id} [GET]",
        ) as response:
            if response.status_code in [200, 401, 404]:
                response.success()
            else:
                response.failure(f"Get task failed: {response.status_code}")


class BSAIAdminUser(HttpUser):
    """Simulates an admin user doing monitoring tasks."""

    wait_time = between(5, 10)
    weight = 1  # Less frequent than regular users

    @task(10)
    def health_check(self):
        """Monitor system health."""
        self.client.get("/health")

    @task(5)
    def get_openapi_spec(self):
        """Fetch OpenAPI spec (simulates monitoring tools)."""
        self.client.get("/openapi.json")

    @task(3)
    def access_docs(self):
        """Access API documentation."""
        self.client.get("/docs")


class WebSocketLoadTest(HttpUser):
    """WebSocket connection load test.

    Note: Locust doesn't natively support WebSocket.
    This simulates the HTTP upgrade request pattern.
    For full WebSocket testing, use a dedicated tool.
    """

    wait_time = between(2, 5)
    weight = 1

    @task
    def websocket_upgrade_attempt(self):
        """Simulate WebSocket upgrade request."""
        session_id = str(uuid4())
        headers = {
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
            "Sec-WebSocket-Version": "13",
        }

        with self.client.get(
            f"/api/v1/ws/{session_id}",
            headers=headers,
            catch_response=True,
            name="/api/v1/ws/{session_id} [WS]",
        ) as response:
            # WebSocket upgrade returns 101 or fails with 4xx
            if response.status_code in [101, 400, 401, 403, 426]:
                response.success()
            else:
                response.failure(f"WebSocket upgrade failed: {response.status_code}")
