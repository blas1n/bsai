"""Dependency Graph for parallel execution.

Builds and manages task dependency graphs to determine
which tasks can be executed in parallel.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class TaskNode:
    """Node in dependency graph."""

    id: str
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, completed, failed


class DependencyGraph:
    """Dependency graph for task execution ordering."""

    def __init__(self, tasks: list[dict[str, Any]]) -> None:
        """Build graph from task list.

        Args:
            tasks: List of task dicts with id, dependencies, status
        """
        self.nodes: dict[str, TaskNode] = {}
        self.dependents: dict[str, set[str]] = defaultdict(set)

        for task in tasks:
            node = TaskNode(
                id=task["id"],
                dependencies=task.get("dependencies", []),
                status=task.get("status", "pending"),
            )
            self.nodes[node.id] = node

            # Build reverse dependency map
            for dep_id in node.dependencies:
                self.dependents[dep_id].add(node.id)

        self._validate_graph()

    def _validate_graph(self) -> None:
        """Validate graph has no cycles."""
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            node = self.nodes.get(node_id)
            if node:
                for dep_id in node.dependencies:
                    if dep_id not in visited:
                        if has_cycle(dep_id):
                            return True
                    elif dep_id in rec_stack:
                        return True

            rec_stack.remove(node_id)
            return False

        for node_id in self.nodes:
            if node_id not in visited:
                if has_cycle(node_id):
                    raise ValueError(f"Cycle detected in dependency graph at {node_id}")

    def get_ready_tasks(self) -> list[str]:
        """Get tasks that can be executed now.

        A task is ready if:
        - Status is 'pending'
        - All dependencies are 'completed'

        Returns:
            List of task IDs that can be executed in parallel
        """
        ready = []

        for node_id, node in self.nodes.items():
            if node.status != "pending":
                continue

            # Check all dependencies are completed
            deps_completed = all(
                self.nodes[dep_id].status == "completed"
                for dep_id in node.dependencies
                if dep_id in self.nodes
            )

            if deps_completed:
                ready.append(node_id)

        return ready

    def mark_in_progress(self, task_id: str) -> None:
        """Mark task as in progress."""
        if task_id in self.nodes:
            self.nodes[task_id].status = "in_progress"

    def mark_completed(self, task_id: str) -> None:
        """Mark task as completed."""
        if task_id in self.nodes:
            self.nodes[task_id].status = "completed"
            logger.debug("task_completed", task_id=task_id)

    def mark_failed(self, task_id: str) -> None:
        """Mark task as failed."""
        if task_id in self.nodes:
            self.nodes[task_id].status = "failed"
            logger.debug("task_failed", task_id=task_id)

    def is_all_completed(self) -> bool:
        """Check if all tasks are completed."""
        return all(node.status in ("completed", "failed") for node in self.nodes.values())

    def get_blocked_tasks(self) -> list[str]:
        """Get tasks blocked by failed dependencies."""
        blocked = []

        for node_id, node in self.nodes.items():
            if node.status != "pending":
                continue

            # Check if any dependency failed
            for dep_id in node.dependencies:
                if dep_id in self.nodes and self.nodes[dep_id].status == "failed":
                    blocked.append(node_id)
                    break

        return blocked

    def get_execution_order(self) -> Iterator[list[str]]:
        """Get execution order as batches of parallel tasks.

        Yields:
            Lists of task IDs that can be executed in parallel
        """
        # Create a copy to simulate execution
        temp_graph = DependencyGraph(
            [
                {
                    "id": node.id,
                    "dependencies": node.dependencies.copy(),
                    "status": "pending",
                }
                for node in self.nodes.values()
            ]
        )

        while not temp_graph.is_all_completed():
            ready = temp_graph.get_ready_tasks()
            if not ready:
                # No ready tasks but not all completed = blocked
                break

            yield ready

            for task_id in ready:
                temp_graph.mark_completed(task_id)

    def get_stats(self) -> dict[str, int]:
        """Get graph statistics."""
        completed = sum(1 for n in self.nodes.values() if n.status == "completed")
        failed = sum(1 for n in self.nodes.values() if n.status == "failed")
        pending = sum(1 for n in self.nodes.values() if n.status == "pending")
        in_progress = sum(1 for n in self.nodes.values() if n.status == "in_progress")

        return {
            "total": len(self.nodes),
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "in_progress": in_progress,
            "parallelizable": len(self.get_ready_tasks()),
        }
