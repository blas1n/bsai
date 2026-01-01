"""Shared fixtures for node tests."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.graph.state import AgentState, MilestoneData
from agent.llm import LLMModel


@pytest.fixture
def mock_config(mock_container: MagicMock) -> RunnableConfig:
    """Create mock RunnableConfig with container."""
    return RunnableConfig(configurable={"ws_manager": None, "container": mock_container})


@pytest.fixture
def mock_container() -> MagicMock:
    """Create mock container with all dependencies."""
    container = MagicMock()
    container.llm_client = MagicMock()
    container.router = MagicMock()
    container.prompt_manager = MagicMock()

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
def base_state() -> AgentState:
    """Create base state for tests."""
    return AgentState(
        session_id=uuid4(),
        task_id=uuid4(),
        original_request="Build a web scraper",
        task_status=TaskStatus.PENDING,
        milestones=[],
        current_milestone_index=0,
        retry_count=0,
        context_messages=[],
        current_context_tokens=0,
        max_context_tokens=100000,
        needs_compression=False,
        workflow_complete=False,
        should_continue=True,
    )


@pytest.fixture
def state_with_milestone(base_state: AgentState) -> AgentState:
    """Create state with a milestone."""
    milestone = MilestoneData(
        id=uuid4(),
        description="Setup project",
        complexity=TaskComplexity.SIMPLE,
        acceptance_criteria="Project initialized",
        status=MilestoneStatus.PENDING,
        selected_model=None,
        generated_prompt=None,
        worker_output=None,
        qa_feedback=None,
        retry_count=0,
    )
    # Create a copy of base_state and override milestones
    state = dict(base_state)
    state["milestones"] = [milestone]
    return AgentState(**state)  # type: ignore[misc]
