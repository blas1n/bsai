"""Core agent implementations.

Seven specialized agents for LLM orchestration:
- Architect: Hierarchical project planning
- Conductor: Request analysis and milestone breakdown
- Meta Prompter: Optimized prompt generation
- Worker: Task execution
- QA Agent: Output validation
- Summarizer: Context compression
- Responder: Final user-facing response generation
"""

from .architect import ArchitectAgent
from .conductor import ConductorAgent
from .meta_prompter import MetaPrompterAgent
from .qa_agent import QAAgent, QADecision
from .responder import ResponderAgent
from .summarizer import SummarizerAgent
from .worker import WorkerAgent

__all__ = [
    "ArchitectAgent",
    "ConductorAgent",
    "MetaPrompterAgent",
    "WorkerAgent",
    "QAAgent",
    "QADecision",
    "SummarizerAgent",
    "ResponderAgent",
]
