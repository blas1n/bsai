"""Dependency injection container module.

Exports:
    ContainerState: Immutable dataclass holding dependencies
    lifespan: Async context manager for container lifecycle
"""

from .container import ContainerState, lifespan

__all__ = [
    "ContainerState",
    "lifespan",
]
