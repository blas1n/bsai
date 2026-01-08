"""Tests for workflow graph composition."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.graph.nodes import Node
from agent.graph.workflow import WorkflowRunner, build_workflow, compile_workflow


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
        assert runner.ws_manager is None

    def test_initialization_with_ws_manager(self, mock_session: AsyncMock) -> None:
        """Test WorkflowRunner initialization with WebSocket manager."""
        mock_ws_manager = MagicMock()
        runner = WorkflowRunner(mock_session, ws_manager=mock_ws_manager)

        assert runner.session is mock_session
        assert runner.ws_manager is mock_ws_manager

    @pytest.mark.asyncio
    async def test_run_calls_ainvoke(self, mock_session: AsyncMock) -> None:
        """Test that run calls ainvoke on the graph."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
            patch("agent.graph.workflow.SessionRepository") as mock_session_repo_class,
            patch.object(
                WorkflowRunner,
                "_load_previous_context",
                new_callable=AsyncMock,
                return_value=([], None, 0),
            ),
            patch.object(
                WorkflowRunner,
                "_load_previous_milestones",
                new_callable=AsyncMock,
                return_value=([], 0),
            ),
        ):
            # Setup mock container from lifespan context manager
            mock_container = MagicMock()
            mock_lifespan.return_value.__aenter__ = AsyncMock(return_value=mock_container)
            mock_lifespan.return_value.__aexit__ = AsyncMock(return_value=None)

            # Setup mock session repository
            mock_session_obj = MagicMock()
            mock_session_obj.user_id = "test-user-123"
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session_obj)
            mock_session_repo_class.return_value = mock_session_repo

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "task_status": TaskStatus.COMPLETED,
                    "workflow_complete": True,
                }
            )
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(mock_session)

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
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
            patch("agent.graph.workflow.SessionRepository") as mock_session_repo_class,
            patch.object(
                WorkflowRunner,
                "_load_previous_context",
                new_callable=AsyncMock,
                return_value=([], None, 0),
            ),
            patch.object(
                WorkflowRunner,
                "_load_previous_milestones",
                new_callable=AsyncMock,
                return_value=([], 0),
            ),
        ):
            mock_container = MagicMock()
            mock_lifespan.return_value.__aenter__ = AsyncMock(return_value=mock_container)
            mock_lifespan.return_value.__aexit__ = AsyncMock(return_value=None)

            # Setup mock session repository
            mock_session_obj = MagicMock()
            mock_session_obj.user_id = "test-user-123"
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session_obj)
            mock_session_repo_class.return_value = mock_session_repo

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "task_status": TaskStatus.COMPLETED,
                }
            )
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(mock_session)

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
    async def test_run_with_custom_max_tokens(self, mock_session: AsyncMock) -> None:
        """Test that run accepts custom max_context_tokens."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
            patch("agent.graph.workflow.SessionRepository") as mock_session_repo_class,
            patch.object(
                WorkflowRunner,
                "_load_previous_context",
                new_callable=AsyncMock,
                return_value=([], None, 0),
            ),
            patch.object(
                WorkflowRunner,
                "_load_previous_milestones",
                new_callable=AsyncMock,
                return_value=([], 0),
            ),
        ):
            mock_container = MagicMock()
            mock_lifespan.return_value.__aenter__ = AsyncMock(return_value=mock_container)
            mock_lifespan.return_value.__aexit__ = AsyncMock(return_value=None)

            # Setup mock session repository
            mock_session_obj = MagicMock()
            mock_session_obj.user_id = "test-user-123"
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session_obj)
            mock_session_repo_class.return_value = mock_session_repo

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "task_status": TaskStatus.COMPLETED,
                }
            )
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(mock_session)

            await runner.run(
                session_id=str(uuid4()),
                task_id=str(uuid4()),
                original_request="Test request",
                max_context_tokens=50000,
            )

            call_args = mock_compiled.ainvoke.call_args[0][0]
            assert call_args["max_context_tokens"] == 50000

    @pytest.mark.asyncio
    async def test_run_passes_container_in_config(self, mock_session: AsyncMock) -> None:
        """Test that run passes container in config to ainvoke."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
            patch("agent.graph.workflow.SessionRepository") as mock_session_repo_class,
            patch.object(
                WorkflowRunner,
                "_load_previous_context",
                new_callable=AsyncMock,
                return_value=([], None, 0),
            ),
            patch.object(
                WorkflowRunner,
                "_load_previous_milestones",
                new_callable=AsyncMock,
                return_value=([], 0),
            ),
        ):
            mock_container = MagicMock()
            mock_lifespan.return_value.__aenter__ = AsyncMock(return_value=mock_container)
            mock_lifespan.return_value.__aexit__ = AsyncMock(return_value=None)

            # Setup mock session repository
            mock_session_obj = MagicMock()
            mock_session_obj.user_id = "test-user-123"
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session_obj)
            mock_session_repo_class.return_value = mock_session_repo

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "task_status": TaskStatus.COMPLETED,
                }
            )
            mock_compile.return_value = mock_compiled

            mock_ws_manager = MagicMock()
            runner = WorkflowRunner(mock_session, ws_manager=mock_ws_manager)

            await runner.run(
                session_id=str(uuid4()),
                task_id=str(uuid4()),
                original_request="Test request",
            )

            # Check config was passed correctly
            call_config = mock_compiled.ainvoke.call_args[1]["config"]
            assert call_config["configurable"]["container"] is mock_container
            assert call_config["configurable"]["ws_manager"] is mock_ws_manager

    @pytest.mark.asyncio
    async def test_run_uses_lifespan_context(self, mock_session: AsyncMock) -> None:
        """Test that run uses lifespan context manager."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
            patch("agent.graph.workflow.SessionRepository") as mock_session_repo_class,
            patch.object(
                WorkflowRunner,
                "_load_previous_context",
                new_callable=AsyncMock,
                return_value=([], None, 0),
            ),
            patch.object(
                WorkflowRunner,
                "_load_previous_milestones",
                new_callable=AsyncMock,
                return_value=([], 0),
            ),
        ):
            mock_container = MagicMock()
            mock_lifespan.return_value.__aenter__ = AsyncMock(return_value=mock_container)
            mock_lifespan.return_value.__aexit__ = AsyncMock(return_value=None)

            # Setup mock session repository
            mock_session_obj = MagicMock()
            mock_session_obj.user_id = "test-user-123"
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session_obj)
            mock_session_repo_class.return_value = mock_session_repo

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "task_status": TaskStatus.COMPLETED,
                }
            )
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(mock_session)

            await runner.run(
                session_id=str(uuid4()),
                task_id=str(uuid4()),
                original_request="Test request",
            )

            # Verify lifespan was called with session
            mock_lifespan.assert_called_once_with(mock_session)
