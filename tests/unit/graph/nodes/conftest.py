"""Shared fixtures for node tests."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import TaskStatus
from agent.events.bus import EventBus
from agent.graph.state import AgentState
from agent.llm import LLMModel
from agent.services import BreakpointService


@pytest.fixture
def mock_ws_manager() -> MagicMock:
    """Create mock WebSocket manager."""
    manager = MagicMock()
    manager.send_message = AsyncMock()
    manager.register_mcp_executor = MagicMock()
    return manager


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Create mock event bus."""
    event_bus = MagicMock(spec=EventBus)
    event_bus.emit = AsyncMock()
    return event_bus


@pytest.fixture
def mock_breakpoint_service() -> MagicMock:
    """Create mock breakpoint service."""
    service = MagicMock(spec=BreakpointService)
    service.is_breakpoint_enabled = MagicMock(return_value=False)
    service.is_paused_at = MagicMock(return_value=False)
    service.set_paused_at = MagicMock()
    service.clear_paused_at = MagicMock()
    return service


@pytest.fixture
def mock_config(
    mock_container: MagicMock,
    mock_ws_manager: MagicMock,
    mock_event_bus: MagicMock,
    mock_breakpoint_service: MagicMock,
) -> RunnableConfig:
    """Create mock RunnableConfig with all required dependencies."""
    return RunnableConfig(
        configurable={
            "ws_manager": mock_ws_manager,
            "container": mock_container,
            "event_bus": mock_event_bus,
            "breakpoint_service": mock_breakpoint_service,
        }
    )


@pytest.fixture
def mock_container() -> MagicMock:
    """Create mock container with all dependencies."""
    container = MagicMock()
    container.llm_client = MagicMock()
    container.router = MagicMock()
    container.prompt_manager = MagicMock()
    container.embedding_service = MagicMock()

    # Ensure prompt_manager.render returns a string (required for Pydantic validation)
    container.prompt_manager.render.return_value = "Mocked rendered prompt content"

    # Ensure embedding_service.embed_with_cache is properly async-mocked
    container.embedding_service.embed_with_cache = AsyncMock(return_value=[0.1] * 1536)

    container.router.select_model.return_value = LLMModel(
        name="gpt-4o-mini",
        provider="openai",
        input_price_per_1k=Decimal("0.00015"),
        output_price_per_1k=Decimal("0.0006"),
        context_window=128000,
        supports_streaming=True,
    )

    return container


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_project_plan() -> MagicMock:
    """Create mock project plan."""
    plan = MagicMock()
    plan.id = uuid4()
    plan.plan_data = {
        "tasks": [
            {
                "id": "T1",
                "description": "Setup project",
                "complexity": "SIMPLE",
                "acceptance_criteria": "Project initialized",
                "status": "pending",
            }
        ]
    }
    plan.total_tasks = 1
    plan.completed_tasks = 0
    plan.structure_type = "flat"
    return plan


@pytest.fixture
def base_state() -> AgentState:
    """Create base state for tests."""
    return AgentState(
        session_id=uuid4(),
        task_id=uuid4(),
        user_id="test-user-123",
        original_request="Build a web scraper",
        task_status=TaskStatus.PENDING,
        retry_count=0,
        context_messages=[],
        current_context_tokens=0,
        max_context_tokens=100000,
        workflow_complete=False,
        should_continue=True,
    )


@pytest.fixture
def state_with_project_plan(base_state: AgentState, mock_project_plan: MagicMock) -> AgentState:
    """Create state with a project plan."""
    return AgentState(
        session_id=base_state["session_id"],
        task_id=base_state["task_id"],
        user_id=base_state["user_id"],
        original_request=base_state["original_request"],
        task_status=base_state.get("task_status", TaskStatus.PENDING),
        project_plan=mock_project_plan,
        current_task_id="T1",
        retry_count=base_state.get("retry_count", 0),
        context_messages=base_state.get("context_messages", []),
        current_context_tokens=base_state.get("current_context_tokens", 0),
        max_context_tokens=base_state.get("max_context_tokens", 100000),
        workflow_complete=base_state.get("workflow_complete", False),
        should_continue=base_state.get("should_continue", True),
    )
