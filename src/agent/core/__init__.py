"""Core agent implementations.

Five specialized agents for LLM orchestration (simplified workflow):
- Architect: Hierarchical project planning
- Conductor: Request analysis and milestone breakdown (legacy, kept for compatibility)
- Worker: Task execution
- QA Agent: Output validation
- Responder: Final user-facing response generation

Removed agents:
- Meta Prompter: Prompt optimization (removed in simplification)
- Summarizer: Context compression (removed in simplification)
"""

from .architect import ArchitectAgent
from .conductor import ConductorAgent
from .qa_agent import QAAgent, QADecision
from .responder import ResponderAgent
from .worker import WorkerAgent

__all__ = [
    "ArchitectAgent",
    "ConductorAgent",
    "WorkerAgent",
    "QAAgent",
    "QADecision",
    "ResponderAgent",
]
