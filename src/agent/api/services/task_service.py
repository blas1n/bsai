"""Task service module.

This module re-exports the TaskService from the refactored task services package.
The TaskService has been split into:
- TaskService: CRUD operations (this export)
- TaskExecutor: Workflow execution logic
- TaskNotifier: WebSocket event broadcasting

For direct access to the split components, import from agent.services.task.
"""

from agent.services.task import TaskExecutor, TaskNotifier, TaskService

__all__ = [
    "TaskService",
    "TaskExecutor",
    "TaskNotifier",
]
