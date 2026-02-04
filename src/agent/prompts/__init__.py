"""Prompt management for agent templates."""

from .keys import (
    ArchitectPrompts,
    ConductorPrompts,
    QAAgentPrompts,
    ResponderPrompts,
    WorkerPrompts,
)
from .manager import PromptManager

__all__ = [
    "PromptManager",
    "ArchitectPrompts",
    "ConductorPrompts",
    "WorkerPrompts",
    "QAAgentPrompts",
    "ResponderPrompts",
]
