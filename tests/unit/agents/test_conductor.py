"""Tests for ConductorAgent."""

from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.core.conductor import ConductorAgent
from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.graph.state import MilestoneData
from agent.llm import LLMModel, LLMResponse, UsageInfo


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create mock LLM client."""
    client = MagicMock()
    client.chat_completion = AsyncMock()
    return client


@pytest.fixture
def mock_router() -> MagicMock:
    """Create mock LLM router."""
    router = MagicMock()
    router.select_model.return_value = LLMModel(
        name="gpt-4o-mini",
        provider="openai",
        input_price_per_1k=Decimal("0.00015"),
        output_price_per_1k=Decimal("0.0006"),
        context_window=128000,
        supports_streaming=True,
    )
    router.calculate_cost.return_value = Decimal("0.001")
    return router


@pytest.fixture
def mock_prompt_manager() -> MagicMock:
    """Create mock PromptManager."""
    manager = MagicMock()
    manager.render.return_value = "Mocked prompt"
    return manager


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def conductor(
    mock_llm_client: MagicMock,
    mock_router: MagicMock,
    mock_prompt_manager: MagicMock,
    mock_session: AsyncMock,
) -> ConductorAgent:
    """Create ConductorAgent with mocked dependencies."""
    agent = ConductorAgent(
        llm_client=mock_llm_client,
        router=mock_router,
        prompt_manager=mock_prompt_manager,
        session=mock_session,
    )
    # Mock the milestone_repo that gets created internally
    agent.milestone_repo = MagicMock()
    agent.milestone_repo.create = AsyncMock()
    return agent


class TestConductorAgent:
    """Test ConductorAgent functionality."""

    @pytest.mark.asyncio
    async def test_analyze_and_plan_success(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
        mock_router: MagicMock,
        mock_prompt_manager: MagicMock,
    ) -> None:
        """Test successful task analysis and planning."""
        task_id = uuid4()
        original_request = "Build a web scraper"

        # Mock LLM response with valid JSON
        mock_response = LLMResponse(
            content='{"milestones": [{"description": "Initialize repo", "complexity": "SIMPLE", "acceptance_criteria": "Repo created"}]}',
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        milestones = await conductor.analyze_and_plan(task_id, original_request)

        # Verify
        assert len(milestones) == 1
        assert milestones[0]["description"] == "Initialize repo"
        assert milestones[0]["complexity"] == TaskComplexity.SIMPLE
        assert milestones[0]["acceptance_criteria"] == "Repo created"

        mock_router.select_model.assert_called_once_with(TaskComplexity.TRIVIAL)
        mock_prompt_manager.render.assert_called_once()
        mock_llm_client.chat_completion.assert_called_once()
        cast(MagicMock, conductor.milestone_repo.create).assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_and_plan_invalid_json(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test error handling for invalid JSON response."""
        task_id = uuid4()
        original_request = "Build a web scraper"

        # Mock LLM response with invalid JSON
        mock_response = LLMResponse(
            content="Invalid JSON response",
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Should raise ValueError
        with pytest.raises(ValueError, match="Failed to parse Conductor response"):
            await conductor.analyze_and_plan(task_id, original_request)

    @pytest.mark.asyncio
    async def test_analyze_and_plan_missing_milestones_key(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test error handling when milestones key is missing."""
        task_id = uuid4()
        original_request = "Build a web scraper"

        # Mock LLM response with valid JSON but missing milestones
        mock_response = LLMResponse(
            content='{"error": "no milestones"}',
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Should raise ValueError
        with pytest.raises(ValueError, match="Failed to parse Conductor response"):
            await conductor.analyze_and_plan(task_id, original_request)

    @pytest.mark.asyncio
    async def test_analyze_and_plan_complexity_validation(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test complexity validation - invalid complexity raises error."""
        task_id = uuid4()
        original_request = "Build a web scraper"

        # Mock LLM response with invalid complexity
        # With structured output, Pydantic will reject invalid complexity values
        mock_response = LLMResponse(
            content='{"milestones": [{"description": "Test", "complexity": "INVALID", "acceptance_criteria": "Done"}]}',
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Should raise ValueError due to Pydantic validation failure
        with pytest.raises(ValueError, match="Failed to parse Conductor response"):
            await conductor.analyze_and_plan(task_id, original_request)

    @pytest.mark.asyncio
    async def test_analyze_and_plan_multiple_milestones(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test handling multiple milestones."""
        task_id = uuid4()
        original_request = "Build a web scraper"

        # Mock LLM response with multiple milestones
        mock_response = LLMResponse(
            content='{"milestones": [{"description": "D1", "complexity": "SIMPLE", "acceptance_criteria": "AC1"}, {"description": "D2", "complexity": "COMPLEX", "acceptance_criteria": "AC2"}]}',
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        milestones = await conductor.analyze_and_plan(task_id, original_request)

        # Verify
        assert len(milestones) == 2
        assert milestones[0]["complexity"] == TaskComplexity.SIMPLE
        assert milestones[1]["complexity"] == TaskComplexity.COMPLEX

        # Should create both milestones in DB
        assert cast(MagicMock, conductor.milestone_repo.create).call_count == 2

    @pytest.mark.asyncio
    async def test_analyze_and_plan_with_sequence_offset(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test milestone sequence numbering with offset for multi-task sessions."""
        task_id = uuid4()
        original_request = "Add feature"
        sequence_offset = 3  # Previous task had 3 milestones

        # Mock LLM response with 2 milestones
        mock_response = LLMResponse(
            content='{"milestones": [{"description": "D1", "complexity": "SIMPLE", "acceptance_criteria": "AC1"}, {"description": "D2", "complexity": "MODERATE", "acceptance_criteria": "AC2"}]}',
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute with sequence offset
        milestones = await conductor.analyze_and_plan(
            task_id, original_request, sequence_offset=sequence_offset
        )

        # Verify milestones created
        assert len(milestones) == 2
        assert cast(MagicMock, conductor.milestone_repo.create).call_count == 2

        # Verify sequence numbers include offset (4, 5 instead of 1, 2)
        mock_create = cast(MagicMock, conductor.milestone_repo.create)
        first_call = mock_create.call_args_list[0]
        second_call = mock_create.call_args_list[1]

        assert first_call.kwargs["sequence_number"] == 4  # offset + 1
        assert second_call.kwargs["sequence_number"] == 5  # offset + 2

    @pytest.mark.asyncio
    async def test_analyze_and_plan_without_sequence_offset(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test milestone sequence numbering defaults to 1-based without offset."""
        task_id = uuid4()
        original_request = "Add feature"

        # Mock LLM response
        mock_response = LLMResponse(
            content='{"milestones": [{"description": "D1", "complexity": "SIMPLE", "acceptance_criteria": "AC1"}]}',
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute without offset (default)
        await conductor.analyze_and_plan(task_id, original_request)

        # Verify sequence starts at 1
        call_args = cast(MagicMock, conductor.milestone_repo.create).call_args
        assert call_args.kwargs["sequence_number"] == 1


class TestConductorReplan:
    """Tests for ConductorAgent replanning functionality."""

    @staticmethod
    def _make_milestone(
        description: str = "Test milestone",
        complexity: TaskComplexity = TaskComplexity.SIMPLE,
        status: MilestoneStatus = MilestoneStatus.PENDING,
    ) -> MilestoneData:
        """Helper to create test milestone."""
        return MilestoneData(
            id=uuid4(),
            description=description,
            complexity=complexity,
            acceptance_criteria="Test criteria",
            status=status,
            selected_model="gpt-4o-mini",
            generated_prompt=None,
            worker_output=None,
            qa_feedback=None,
            retry_count=0,
        )

    @pytest.mark.asyncio
    async def test_replan_based_on_execution_success(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test successful replanning."""
        task_id = uuid4()
        original_request = "Build a web scraper"
        milestones = [
            self._make_milestone("First", status=MilestoneStatus.PASSED),
            self._make_milestone("Second", status=MilestoneStatus.IN_PROGRESS),
        ]

        # Mock LLM response with valid replan output
        mock_response = LLMResponse(
            content="""{
                "analysis": "Current approach has issues",
                "modifications": [{
                    "action": "ADD",
                    "reason": "Need intermediate step",
                    "new_milestone": {
                        "description": "New step",
                        "complexity": "SIMPLE",
                        "acceptance_criteria": "Step done"
                    }
                }],
                "confidence": 0.9,
                "reasoning": "Adding step to fix the issue"
            }""",
            usage=UsageInfo(input_tokens=200, output_tokens=100, total_tokens=300),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        result = await conductor.replan_based_on_execution(
            task_id=task_id,
            original_request=original_request,
            current_milestones=milestones,
            current_milestone_index=1,
            worker_observations=["Found unexpected data format"],
            qa_feedback="Output doesn't match criteria",
            replan_reason="Plan needs revision",
        )

        # Verify
        assert result.analysis == "Current approach has issues"
        assert len(result.modifications) == 1
        assert result.modifications[0].action == "ADD"
        assert result.confidence == 0.9
        mock_llm_client.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_replan_with_modify_action(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test replanning with MODIFY action."""
        task_id = uuid4()
        milestones = [
            self._make_milestone("First", status=MilestoneStatus.PASSED),
            self._make_milestone("Second", status=MilestoneStatus.IN_PROGRESS),
            self._make_milestone("Third"),
        ]

        # Mock response with MODIFY action
        mock_response = LLMResponse(
            content="""{
                "analysis": "Third milestone needs adjustment",
                "modifications": [{
                    "action": "MODIFY",
                    "target_index": 2,
                    "reason": "Requirements changed",
                    "new_milestone": {
                        "description": "Modified third",
                        "complexity": "MODERATE",
                        "acceptance_criteria": "Updated criteria"
                    }
                }],
                "confidence": 0.85,
                "reasoning": "Adjusting for new requirements"
            }""",
            usage=UsageInfo(input_tokens=200, output_tokens=100, total_tokens=300),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        result = await conductor.replan_based_on_execution(
            task_id=task_id,
            original_request="Original request",
            current_milestones=milestones,
            current_milestone_index=1,
            worker_observations=[],
            qa_feedback="Plan viability issue",
            replan_reason="NEEDS_REVISION",
        )

        # Verify
        assert len(result.modifications) == 1
        assert result.modifications[0].action == "MODIFY"
        assert result.modifications[0].target_index == 2

    @pytest.mark.asyncio
    async def test_replan_with_remove_action(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test replanning with REMOVE action."""
        task_id = uuid4()
        milestones = [
            self._make_milestone("First", status=MilestoneStatus.PASSED),
            self._make_milestone("Second", status=MilestoneStatus.IN_PROGRESS),
            self._make_milestone("Third"),
            self._make_milestone("Fourth"),
        ]

        # Mock response with REMOVE action
        mock_response = LLMResponse(
            content="""{
                "analysis": "Fourth milestone is unnecessary",
                "modifications": [{
                    "action": "REMOVE",
                    "target_index": 3,
                    "reason": "No longer needed"
                }],
                "confidence": 0.95,
                "reasoning": "Simplifying the plan"
            }""",
            usage=UsageInfo(input_tokens=200, output_tokens=100, total_tokens=300),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute
        result = await conductor.replan_based_on_execution(
            task_id=task_id,
            original_request="Original request",
            current_milestones=milestones,
            current_milestone_index=1,
            worker_observations=[],
            qa_feedback="",
            replan_reason="NEEDS_REVISION",
        )

        # Verify
        assert len(result.modifications) == 1
        assert result.modifications[0].action == "REMOVE"
        assert result.modifications[0].target_index == 3

    @pytest.mark.asyncio
    async def test_replan_with_previous_replans(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test replanning considers previous replan history."""
        task_id = uuid4()
        milestones = [self._make_milestone("Current")]
        previous_replans = [
            {
                "iteration": 1,
                "reason": "First replan",
                "modifications": [{"action": "ADD"}],
            }
        ]

        mock_response = LLMResponse(
            content="""{
                "analysis": "Second replan needed",
                "modifications": [],
                "confidence": 0.7,
                "reasoning": "Adjusting after first replan"
            }""",
            usage=UsageInfo(input_tokens=200, output_tokens=100, total_tokens=300),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Execute with previous replans
        result = await conductor.replan_based_on_execution(
            task_id=task_id,
            original_request="Request",
            current_milestones=milestones,
            current_milestone_index=0,
            worker_observations=[],
            qa_feedback="",
            replan_reason="Second issue",
            previous_replans=previous_replans,
        )

        # Verify LLM was called with previous replan context
        mock_llm_client.chat_completion.assert_called_once()
        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_replan_invalid_json_raises_error(
        self,
        conductor: ConductorAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test error handling for invalid JSON response."""
        task_id = uuid4()
        milestones = [self._make_milestone("Test")]

        # Mock invalid JSON response
        mock_response = LLMResponse(
            content="Invalid JSON",
            usage=UsageInfo(input_tokens=100, output_tokens=50, total_tokens=150),
            model="test-model",
        )
        mock_llm_client.chat_completion.return_value = mock_response

        # Should raise ValueError
        with pytest.raises(ValueError, match="Failed to parse Conductor replan response"):
            await conductor.replan_based_on_execution(
                task_id=task_id,
                original_request="Request",
                current_milestones=milestones,
                current_milestone_index=0,
                worker_observations=[],
                qa_feedback="",
                replan_reason="Issue",
            )
