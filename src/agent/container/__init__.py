"""Dependency injection container module.

Exports:
    AgentContainer: Singleton DI container class
    get_container: Module-level accessor function
    reset_container: Reset for testing
"""

from .container import AgentContainer

__all__ = [
    "AgentContainer",
    "get_container",
    "reset_container",
]

# Module-level singleton accessor
_container: AgentContainer | None = None


def get_container() -> AgentContainer:
    """Get the global container singleton.

    Returns:
        The global AgentContainer instance
    """
    global _container
    if _container is None:
        _container = AgentContainer.get_instance()
    return _container


def reset_container() -> None:
    """Reset the global container singleton.

    Useful for testing to ensure clean state between tests.
    """
    global _container
    AgentContainer.reset()
    _container = None
