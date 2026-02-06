"""Prompt management for agent templates."""

from .keys import (
    ArchitectPrompts,
    QAAgentPrompts,
    ResponderPrompts,
    WorkerPrompts,
)
from .manager import PromptManager

__all__ = [
    "PromptManager",
    "ArchitectPrompts",
    "WorkerPrompts",
    "QAAgentPrompts",
    "ResponderPrompts",
]
