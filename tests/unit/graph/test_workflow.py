"""Tests for workflow graph composition."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.graph.nodes import Node
from agent.graph.workflow import WorkflowResult, WorkflowRunner, build_workflow, compile_workflow


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Create mock event bus."""
    from agent.events.bus import EventBus

    event_bus = MagicMock(spec=EventBus)
    event_bus.emit = AsyncMock()
    return event_bus


@pytest.fixture
def mock_ws_manager() -> MagicMock:
    """Create mock WebSocket manager."""
    from agent.api.websocket.manager import ConnectionManager

    return MagicMock(spec=ConnectionManager)


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create mock session cache."""
    from agent.cache import SessionCache

    cache = MagicMock(spec=SessionCache)
    cache.get_cached_context = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def mock_breakpoint_service() -> MagicMock:
    """Create mock breakpoint service."""
    from agent.services import BreakpointService

    return MagicMock(spec=BreakpointService)


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

    def test_initialization(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test WorkflowRunner initialization."""
        runner = WorkflowRunner(
            mock_session,
            ws_manager=mock_ws_manager,
            cache=mock_cache,
            event_bus=mock_event_bus,
            breakpoint_service=mock_breakpoint_service,
        )

        assert runner.session is mock_session
        assert runner.ws_manager is mock_ws_manager
        assert runner.cache is mock_cache
        assert runner.event_bus is mock_event_bus
        assert runner.breakpoint_service is mock_breakpoint_service

    def test_initialization_stores_all_dependencies(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test WorkflowRunner stores all dependencies."""
        runner = WorkflowRunner(
            mock_session,
            ws_manager=mock_ws_manager,
            cache=mock_cache,
            event_bus=mock_event_bus,
            breakpoint_service=mock_breakpoint_service,
        )

        assert runner.session is mock_session
        assert runner.ws_manager is mock_ws_manager

    def test_initialization_requires_all_arguments(self, mock_session: AsyncMock) -> None:
        """Test WorkflowRunner requires all arguments."""
        with pytest.raises(TypeError):
            WorkflowRunner(mock_session)  # type: ignore[call-arg]

    @pytest.mark.asyncio
    async def test_run_calls_ainvoke(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that run calls ainvoke on the graph."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
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

            # Setup mock checkpointer context manager
            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

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
            # Mock aget_state to return no pending nodes (not interrupted)
            mock_graph_state = MagicMock()
            mock_graph_state.next = ()  # Empty tuple means no pending nodes
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

            session_id = str(uuid4())
            task_id = str(uuid4())

            result = await runner.run(
                session_id=session_id,
                task_id=task_id,
                original_request="Test request",
            )

            mock_compiled.ainvoke.assert_called_once()
            assert isinstance(result, WorkflowResult)
            assert result.state.get("task_status") == TaskStatus.COMPLETED
            assert result.interrupted is False

    @pytest.mark.asyncio
    async def test_run_accepts_uuid(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that run accepts UUID objects."""
        from uuid import UUID, uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
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

            # Setup mock checkpointer context manager
            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

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
            # Mock aget_state
            mock_graph_state = MagicMock()
            mock_graph_state.next = ()
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

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
    async def test_run_with_custom_max_tokens(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that run accepts custom max_context_tokens."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
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

            # Setup mock checkpointer context manager
            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

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
            # Mock aget_state
            mock_graph_state = MagicMock()
            mock_graph_state.next = ()
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

            await runner.run(
                session_id=str(uuid4()),
                task_id=str(uuid4()),
                original_request="Test request",
                max_context_tokens=50000,
            )

            call_args = mock_compiled.ainvoke.call_args[0][0]
            assert call_args["max_context_tokens"] == 50000

    @pytest.mark.asyncio
    async def test_run_passes_container_in_config(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that run passes container in config to ainvoke."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
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

            # Setup mock checkpointer context manager
            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

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
            # Mock aget_state
            mock_graph_state = MagicMock()
            mock_graph_state.next = ()
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

            await runner.run(
                session_id=str(uuid4()),
                task_id=str(uuid4()),
                original_request="Test request",
            )

            # Check config was passed correctly
            call_config = mock_compiled.ainvoke.call_args[1]["config"]
            assert call_config["configurable"]["container"] is mock_container
            assert call_config["configurable"]["ws_manager"] is mock_ws_manager
            assert call_config["configurable"]["event_bus"] is mock_event_bus

    @pytest.mark.asyncio
    async def test_run_uses_lifespan_context(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that run uses lifespan context manager."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
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

            # Setup mock checkpointer context manager
            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

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
            # Mock aget_state
            mock_graph_state = MagicMock()
            mock_graph_state.next = ()
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

            await runner.run(
                session_id=str(uuid4()),
                task_id=str(uuid4()),
                original_request="Test request",
            )

            # Verify lifespan was called with session
            mock_lifespan.assert_called_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_run_raises_for_missing_session(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that run raises ValueError when session not found."""
        from uuid import uuid4

        with patch("agent.graph.workflow.SessionRepository") as mock_session_repo_class:
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=None)
            mock_session_repo_class.return_value = mock_session_repo

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

            with pytest.raises(ValueError, match="not found"):
                await runner.run(
                    session_id=str(uuid4()),
                    task_id=str(uuid4()),
                    original_request="Test",
                )

    @pytest.mark.asyncio
    async def test_run_returns_interrupted_result(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that run returns interrupted result when workflow is paused."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
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

            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_session_obj = MagicMock()
            mock_session_obj.user_id = "test-user-123"
            mock_session_repo = MagicMock()
            mock_session_repo.get_by_id = AsyncMock(return_value=mock_session_obj)
            mock_session_repo_class.return_value = mock_session_repo

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "task_status": TaskStatus.IN_PROGRESS,
                }
            )
            # Mock aget_state to return pending nodes (interrupted)
            mock_graph_state = MagicMock()
            mock_graph_state.next = ["qa_breakpoint"]
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

            result = await runner.run(
                session_id=str(uuid4()),
                task_id=str(uuid4()),
                original_request="Test request",
            )

            assert result.interrupted is True
            assert result.interrupt_node == "qa_breakpoint"


class TestWorkflowRunnerResume:
    """Tests for WorkflowRunner.resume method."""

    @pytest.mark.asyncio
    async def test_resume_calls_ainvoke(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that resume calls ainvoke on the graph."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_container = MagicMock()
            mock_lifespan.return_value.__aenter__ = AsyncMock(return_value=mock_container)
            mock_lifespan.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(return_value={"task_status": TaskStatus.COMPLETED})
            mock_graph_state = MagicMock()
            mock_graph_state.next = ()
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

            result = await runner.resume(task_id=str(uuid4()))

            mock_compiled.ainvoke.assert_called_once()
            assert result.interrupted is False

    @pytest.mark.asyncio
    async def test_resume_passes_user_input(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that resume passes user_input to ainvoke."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_container = MagicMock()
            mock_lifespan.return_value.__aenter__ = AsyncMock(return_value=mock_container)
            mock_lifespan.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(return_value={"task_status": TaskStatus.COMPLETED})
            mock_graph_state = MagicMock()
            mock_graph_state.next = ()
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )
            user_input = {"user_input": "Modified output", "rejected": False}

            await runner.resume(task_id=str(uuid4()), user_input=user_input)

            call_args = mock_compiled.ainvoke.call_args
            assert call_args[0][0] == user_input

    @pytest.mark.asyncio
    async def test_resume_detects_interrupt(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that resume detects when workflow is interrupted again."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.lifespan") as mock_lifespan,
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_container = MagicMock()
            mock_lifespan.return_value.__aenter__ = AsyncMock(return_value=mock_container)
            mock_lifespan.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_compiled = MagicMock()
            mock_compiled.ainvoke = AsyncMock(return_value={"task_status": TaskStatus.IN_PROGRESS})
            mock_graph_state = MagicMock()
            mock_graph_state.next = ["verify_qa"]  # Another interrupt
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

            result = await runner.resume(task_id=uuid4())

            assert result.interrupted is True
            assert result.interrupt_node == "verify_qa"


class TestWorkflowRunnerGetState:
    """Tests for WorkflowRunner.get_state method."""

    @pytest.mark.asyncio
    async def test_get_state_returns_state(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that get_state returns state from checkpoint."""
        from uuid import uuid4

        from agent.db.models.enums import TaskStatus

        with (
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

            expected_state = {"task_status": TaskStatus.IN_PROGRESS}
            mock_graph_state = MagicMock()
            mock_graph_state.values = expected_state

            mock_compiled = MagicMock()
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

            result = await runner.get_state(uuid4())

            assert result == expected_state

    @pytest.mark.asyncio
    async def test_get_state_returns_none_for_empty(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test that get_state returns None when no state exists."""
        from uuid import uuid4

        with (
            patch("agent.graph.workflow.get_checkpointer") as mock_get_checkpointer,
            patch("agent.graph.workflow.compile_workflow") as mock_compile,
        ):
            mock_checkpointer = MagicMock()
            mock_get_checkpointer.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_get_checkpointer.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_graph_state = MagicMock()
            mock_graph_state.values = {}  # Empty state

            mock_compiled = MagicMock()
            mock_compiled.aget_state = AsyncMock(return_value=mock_graph_state)
            mock_compile.return_value = mock_compiled

            runner = WorkflowRunner(
                mock_session,
                ws_manager=mock_ws_manager,
                cache=mock_cache,
                event_bus=mock_event_bus,
                breakpoint_service=mock_breakpoint_service,
            )

            result = await runner.get_state(str(uuid4()))

            assert result is None


class TestWorkflowRunnerLoadContext:
    """Tests for WorkflowRunner context loading methods."""

    @pytest.mark.asyncio
    async def test_load_previous_context_from_cache(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test loading context from cache."""
        mock_cache = MagicMock()
        mock_cache.get_cached_context = AsyncMock(
            return_value={
                "messages": [{"role": "user", "content": "Hello"}],
                "summary": "User said hello",
                "token_count": 100,
            }
        )

        runner = WorkflowRunner(
            mock_session,
            ws_manager=mock_ws_manager,
            cache=mock_cache,
            event_bus=mock_event_bus,
            breakpoint_service=mock_breakpoint_service,
        )

        from uuid import uuid4

        messages, summary, tokens = await runner._load_previous_context(uuid4())

        assert len(messages) == 1
        assert messages[0].role == "user"
        assert summary == "User said hello"
        assert tokens == 100

    @pytest.mark.asyncio
    async def test_load_previous_context_from_snapshot(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test loading context from memory snapshot."""
        from uuid import uuid4

        mock_cache = MagicMock()
        mock_cache.get_cached_context = AsyncMock(return_value=None)

        runner = WorkflowRunner(
            mock_session,
            ws_manager=mock_ws_manager,
            cache=mock_cache,
            event_bus=mock_event_bus,
            breakpoint_service=mock_breakpoint_service,
        )

        mock_snapshot = MagicMock()
        mock_snapshot.id = uuid4()
        mock_snapshot.compressed_context = "Previous summary"
        mock_snapshot.token_count = 200

        with (
            patch("agent.graph.workflow.MemorySnapshotRepository") as mock_snapshot_repo,
            patch("agent.graph.workflow.ArtifactRepository") as mock_artifact_repo,
        ):
            mock_snapshot_repo.return_value.get_latest_snapshot = AsyncMock(
                return_value=mock_snapshot
            )
            mock_artifact_repo.return_value.get_by_session_id = AsyncMock(return_value=[])

            messages, summary, tokens = await runner._load_previous_context(uuid4())

        assert len(messages) == 1
        assert "Previous summary" in messages[0].content
        assert summary == "Previous summary"
        assert tokens == 200

    @pytest.mark.asyncio
    async def test_load_previous_milestones(
        self,
        mock_session: AsyncMock,
        mock_ws_manager: MagicMock,
        mock_cache: MagicMock,
        mock_event_bus: MagicMock,
        mock_breakpoint_service: MagicMock,
    ) -> None:
        """Test loading previous milestones."""
        from uuid import uuid4

        from agent.db.models.enums import MilestoneStatus, TaskComplexity

        runner = WorkflowRunner(
            mock_session,
            ws_manager=mock_ws_manager,
            cache=mock_cache,
            event_bus=mock_event_bus,
            breakpoint_service=mock_breakpoint_service,
        )

        mock_milestone = MagicMock()
        mock_milestone.id = uuid4()
        mock_milestone.description = "Test milestone"
        mock_milestone.complexity = TaskComplexity.SIMPLE
        mock_milestone.acceptance_criteria = "Must work"
        mock_milestone.status = MilestoneStatus.PASSED
        mock_milestone.selected_llm = "gpt-4"
        mock_milestone.worker_output = "Done"
        mock_milestone.qa_result = "OK"
        mock_milestone.retry_count = 0

        with patch("agent.graph.workflow.MilestoneRepository") as mock_repo:
            mock_repo.return_value.get_by_session_id = AsyncMock(return_value=[mock_milestone])
            mock_repo.return_value.get_max_sequence_for_session = AsyncMock(return_value=1)

            milestones, max_seq = await runner._load_previous_milestones(uuid4())

        assert len(milestones) == 1
        assert milestones[0]["description"] == "Test milestone"
        assert max_seq == 1


class TestCreateNodeWithSession:
    """Tests for _create_node_with_session helper."""

    @pytest.mark.asyncio
    async def test_wraps_node_with_session(self) -> None:
        """Test that node wrapper injects session."""
        from agent.graph.workflow import _create_node_with_session

        mock_session = MagicMock()
        captured_args: dict = {}

        async def sample_node(state, config, session):
            captured_args["state"] = state
            captured_args["config"] = config
            captured_args["session"] = session
            return {"result": "success"}

        wrapped = _create_node_with_session(sample_node, mock_session)

        result = await wrapped({"input": "test"}, {"configurable": {}})

        assert result == {"result": "success"}
        assert captured_args["session"] is mock_session

    def test_preserves_function_name(self) -> None:
        """Test that wrapper preserves original function name."""
        from agent.graph.workflow import _create_node_with_session

        async def my_node(state, config, session):
            return {}

        wrapped = _create_node_with_session(my_node, MagicMock())

        assert wrapped.__name__ == "my_node"
