"""Tests for ArtifactRepository."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.repository.artifact_repo import ArtifactRepository


def _create_mock_artifact(
    task_id,
    filename: str,
    content: str,
    **kwargs,
) -> MagicMock:
    """Create a mock artifact."""
    mock = MagicMock()
    mock.id = kwargs.get("id", uuid4())
    mock.task_id = task_id
    mock.milestone_id = kwargs.get("milestone_id")
    mock.artifact_type = kwargs.get("artifact_type", "code")
    mock.filename = filename
    mock.kind = kwargs.get("kind", "py")
    mock.content = content
    mock.path = kwargs.get("path", "")
    mock.sequence_number = kwargs.get("sequence_number", 0)
    return mock


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def repo(mock_session: AsyncMock) -> ArtifactRepository:
    """Create ArtifactRepository instance."""
    return ArtifactRepository(mock_session)


class TestGetByTaskId:
    """Tests for get_by_task_id method."""

    async def test_get_by_task_id_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting artifacts by task ID."""
        task_id = uuid4()
        artifact1 = _create_mock_artifact(task_id, "main.py", "content1", sequence_number=0)
        artifact2 = _create_mock_artifact(task_id, "utils.py", "content2", sequence_number=1)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [artifact1, artifact2]
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_task_id(task_id)

        assert len(result) == 2
        assert result[0].filename == "main.py"
        assert result[1].filename == "utils.py"

    async def test_get_by_task_id_empty(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting artifacts when none exist."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_task_id(task_id)

        assert result == []


class TestGetByMilestoneId:
    """Tests for get_by_milestone_id method."""

    async def test_get_by_milestone_id_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting artifacts by milestone ID."""
        task_id = uuid4()
        milestone_id = uuid4()
        artifact = _create_mock_artifact(task_id, "main.py", "content", milestone_id=milestone_id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [artifact]
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_milestone_id(milestone_id)

        assert len(result) == 1
        assert result[0].milestone_id == milestone_id

    async def test_get_by_milestone_id_empty(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting artifacts when milestone has none."""
        milestone_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_milestone_id(milestone_id)

        assert result == []


class TestCreateArtifact:
    """Tests for create_artifact method."""

    async def test_create_artifact_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test creating an artifact."""
        task_id = uuid4()

        await repo.create_artifact(
            task_id=task_id,
            artifact_type="code",
            filename="main.py",
            content="print('hello')",
            kind="py",
            path="src",
            sequence_number=0,
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once()

    async def test_create_artifact_with_milestone(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test creating an artifact with milestone."""
        task_id = uuid4()
        milestone_id = uuid4()

        await repo.create_artifact(
            task_id=task_id,
            artifact_type="file",
            filename="config.json",
            content='{"key": "value"}',
            kind="json",
            path="",
            milestone_id=milestone_id,
        )

        mock_session.add.assert_called_once()
        added_artifact = mock_session.add.call_args[0][0]
        assert added_artifact.milestone_id == milestone_id


class TestDeleteByTaskId:
    """Tests for delete_by_task_id method."""

    async def test_delete_by_task_id_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test deleting artifacts by task ID."""
        task_id = uuid4()
        artifact1 = _create_mock_artifact(task_id, "main.py", "content1")
        artifact2 = _create_mock_artifact(task_id, "utils.py", "content2")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [artifact1, artifact2]
        mock_session.execute.return_value = mock_result

        count = await repo.delete_by_task_id(task_id)

        assert count == 2
        assert mock_session.delete.await_count == 2
        mock_session.flush.assert_called_once()

    async def test_delete_by_task_id_empty(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test deleting artifacts when none exist."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        count = await repo.delete_by_task_id(task_id)

        assert count == 0
        mock_session.delete.assert_not_called()


class TestGetCodeArtifacts:
    """Tests for get_code_artifacts method."""

    async def test_get_code_artifacts_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting only code artifacts."""
        task_id = uuid4()
        code_artifact = _create_mock_artifact(
            task_id, "main.py", "print('hello')", artifact_type="code"
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [code_artifact]
        mock_session.execute.return_value = mock_result

        result = await repo.get_code_artifacts(task_id)

        assert len(result) == 1
        assert result[0].artifact_type == "code"

    async def test_get_code_artifacts_empty(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting code artifacts when none exist."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repo.get_code_artifacts(task_id)

        assert result == []


class TestGetBySessionId:
    """Tests for get_by_session_id method."""

    async def test_get_by_session_id_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting artifacts by session ID."""
        session_id = uuid4()
        task_id = uuid4()
        artifact = _create_mock_artifact(task_id, "main.py", "content")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [artifact]
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_session_id(session_id)

        assert len(result) == 1

    async def test_get_by_session_id_with_limit(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting artifacts with custom limit."""
        session_id = uuid4()
        task_id = uuid4()
        artifacts = [_create_mock_artifact(task_id, f"file{i}.py", f"content{i}") for i in range(5)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = artifacts
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_session_id(session_id, limit=5)

        assert len(result) == 5

    async def test_get_by_session_id_empty(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting artifacts when session has none."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_session_id(session_id)

        assert result == []
