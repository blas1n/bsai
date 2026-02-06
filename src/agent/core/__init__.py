"""Core agent implementations.

Simplified 7-node workflow agents:
- Architect: Hierarchical project planning and task breakdown
- Worker: Task execution with MCP tools
- QA Agent: Output validation
- Responder: Final user-facing response generation

Workflow: architect -> plan_review -> execute_worker -> verify_qa
    -> execution_breakpoint -> advance -> generate_response -> END
"""

from .architect import ArchitectAgent
from .qa_agent import QAAgent, QADecision
from .responder import ResponderAgent
from .worker import WorkerAgent

__all__ = [
    "ArchitectAgent",
    "WorkerAgent",
    "QAAgent",
    "QADecision",
    "ResponderAgent",
]
