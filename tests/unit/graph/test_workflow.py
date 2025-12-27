"""Tests for workflow graph composition."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.container import reset_container
from agent.graph.nodes import Node
from agent.graph.workflow import WorkflowRunner, build_workflow, compile_workflow


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset container singleton before each test."""
    reset_container()
    yield
    reset_container()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    return AsyncMock()


class TestBuildWorkflow:
    """Tests for build_workflow function."""

    def test_builds_graph(self, mock_session: AsyncMock) -> None:
        """Test that build_workflow creates a StateGraph."""
        graph = build_workflow(mock_session)

        # Check graph has nodes
        assert graph is not None
        # StateGraph has nodes attribute
        assert hasattr(graph, "nodes")

    def test_graph_has_required_nodes(self, mock_session: AsyncMock) -> None:
        """Test that graph has all required nodes."""
        graph = build_workflow(mock_session)

        # Check all nodes are present (using Node enum)
        for node in Node:
            assert node in graph.nodes, f"Missing node: {node}"


class TestCompileWorkflow:
    """Tests for compile_workflow function."""

    def test_compiles_successfully(self, mock_session: AsyncMock) -> None:
        """Test that workflow compiles without errors."""
        compiled = compile_workflow(mock_session)

        assert compiled is not None

    def test_compiled_has_invoke(self, mock_session: AsyncMock) -> None:
        """Test that compiled graph has invoke method."""
        compiled = compile_workflow(mock_session)

        assert hasattr(compiled, "ainvoke")


class TestWorkflowRunner:
    """Tests for WorkflowRunner class."""

    def test_initialization(self, mock_session: AsyncMock) -> None:
        """Test WorkflowRunner initialization."""
        runner = WorkflowRunner(mock_session)

        assert runner.session is mock_session
        assert runner._compiled is None

    @pytest.mark.asyncio
    async def test_initialize_creates_graph(self, mock_session: AsyncMock) -> None:
        """Test that initialize creates the compiled graph."""
        with (
            patch("agent.graph.workflow.get_container") as mock_get_container,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_container = MagicMock()
            mock_container.is_initialized = False
            mock_container.initialize = AsyncMock()
            mock_get_container.return_value = mock_container

            mock_compiled = MagicMock()
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(mock_session)
            await runner.initialize()

            mock_container.initialize.assert_called_once_with(mock_session)
            mock_compile.assert_called_once_with(mock_session)
            assert runner._compiled is mock_compiled

    def test_graph_before_init_raises(self, mock_session: AsyncMock) -> None:
        """Test accessing graph before initialize raises."""
        runner = WorkflowRunner(mock_session)

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = runner.graph

    @pytest.mark.asyncio
    async def test_graph_after_init_works(self, mock_session: AsyncMock) -> None:
        """Test accessing graph after initialize works."""
        with (
            patch("agent.graph.workflow.get_container") as mock_get_container,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_container = MagicMock()
            mock_container.is_initialized = False
            mock_container.initialize = AsyncMock()
            mock_get_container.return_value = mock_container

            mock_compiled = MagicMock()
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(mock_session)
            await runner.initialize()

            assert runner.graph is mock_compiled

    @pytest.mark.asyncio
    async def test_run_calls_ainvoke(self, mock_session: AsyncMock) -> None:
        """Test that run calls ainvoke on the graph."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.get_container") as mock_get_container,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_container = MagicMock()
            mock_container.is_initialized = True
            mock_get_container.return_value = mock_container

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "task_status": TaskStatus.COMPLETED,
                    "workflow_complete": True,
                }
            )
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(mock_session)
            await runner.initialize()

            session_id = str(uuid4())
            task_id = str(uuid4())

            result = await runner.run(
                session_id=session_id,
                task_id=task_id,
                original_request="Test request",
            )

            mock_compiled.ainvoke.assert_called_once()
            assert result["task_status"] == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_run_accepts_uuid(self, mock_session: AsyncMock) -> None:
        """Test that run accepts UUID objects."""
        from uuid import UUID, uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.get_container") as mock_get_container,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_container = MagicMock()
            mock_container.is_initialized = True
            mock_get_container.return_value = mock_container

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "task_status": TaskStatus.COMPLETED,
                }
            )
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(mock_session)
            await runner.initialize()

            session_id = uuid4()
            task_id = uuid4()

            await runner.run(
                session_id=session_id,
                task_id=task_id,
                original_request="Test request",
            )

            # Check that UUIDs were passed correctly
            call_args = mock_compiled.ainvoke.call_args[0][0]
            assert isinstance(call_args["session_id"], UUID)
            assert isinstance(call_args["task_id"], UUID)

    @pytest.mark.asyncio
    async def test_run_auto_initializes(self, mock_session: AsyncMock) -> None:
        """Test that run auto-initializes if needed."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.get_container") as mock_get_container,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_container = MagicMock()
            mock_container.is_initialized = False
            mock_container.initialize = AsyncMock()
            mock_get_container.return_value = mock_container

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "task_status": TaskStatus.COMPLETED,
                }
            )
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(mock_session)

            # Don't call initialize manually
            result = await runner.run(
                session_id=str(uuid4()),
                task_id=str(uuid4()),
                original_request="Test request",
            )

            # Should have auto-initialized
            mock_container.initialize.assert_called_once()
            assert result["task_status"] == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_run_with_custom_max_tokens(self, mock_session: AsyncMock) -> None:
        """Test that run accepts custom max_context_tokens."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.get_container") as mock_get_container,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_container = MagicMock()
            mock_container.is_initialized = True
            mock_get_container.return_value = mock_container

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "task_status": TaskStatus.COMPLETED,
                }
            )
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(mock_session)
            await runner.initialize()

            await runner.run(
                session_id=str(uuid4()),
                task_id=str(uuid4()),
                original_request="Test request",
                max_context_tokens=50000,
            )

            call_args = mock_compiled.ainvoke.call_args[0][0]
            assert call_args["max_context_tokens"] == 50000
