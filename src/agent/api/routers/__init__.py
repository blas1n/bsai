"""API routers for endpoint organization."""

from .artifacts import router as artifacts_router
from .health import router as health_router
from .mcp import router as mcp_router
from .memories import router as memories_router
from .plan import router as plan_router
from .sessions import router as sessions_router
from .snapshots import router as snapshots_router
from .tasks import router as tasks_router
from .websocket import router as websocket_router

__all__ = [
    "artifacts_router",
    "health_router",
    "mcp_router",
    "memories_router",
    "plan_router",
    "sessions_router",
    "snapshots_router",
    "tasks_router",
    "websocket_router",
]
