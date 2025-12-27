"""API routers for endpoint organization."""

from .health import router as health_router
from .milestones import router as milestones_router
from .sessions import router as sessions_router
from .snapshots import router as snapshots_router
from .tasks import router as tasks_router
from .websocket import router as websocket_router

__all__ = [
    "health_router",
    "sessions_router",
    "tasks_router",
    "milestones_router",
    "snapshots_router",
    "websocket_router",
]
