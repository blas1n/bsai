"""Tests for ArtifactRepository (task-level snapshot system)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent.db.repository.artifact_repo import ArtifactRepository


def _create_mock_artifact(
    session_id,
    filename: str,
    content: str,
    **kwargs,
) -> MagicMock:
    """Create a mock artifact."""
    mock = MagicMock()
    mock.id = kwargs.get("id", uuid4())
    mock.session_id = session_id
    mock.task_id = kwargs.get("task_id", uuid4())
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
        """Test getting artifacts by task ID (snapshot)."""
        session_id = uuid4()
        task_id = uuid4()
        artifact1 = _create_mock_artifact(
            session_id, "main.py", "content1", task_id=task_id, sequence_number=0
        )
        artifact2 = _create_mock_artifact(
            session_id, "utils.py", "content2", task_id=task_id, sequence_number=1
        )

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
        """Test getting artifacts when task has none."""
        task_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_task_id(task_id)

        assert result == []


class TestGetLatestSnapshot:
    """Tests for get_latest_snapshot method."""

    async def test_get_latest_snapshot_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting latest snapshot from completed task."""
        session_id = uuid4()
        task_id = uuid4()
        artifact = _create_mock_artifact(session_id, "main.py", "content", task_id=task_id)

        # First call returns latest task_id
        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        # Second call returns artifacts
        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [artifact]

        mock_session.execute.side_effect = [mock_task_result, mock_artifacts_result]

        result = await repo.get_latest_snapshot(session_id)

        assert len(result) == 1
        assert result[0].filename == "main.py"

    async def test_get_latest_snapshot_no_completed_task(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting latest snapshot when no completed tasks."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.get_latest_snapshot(session_id)

        assert result == []


class TestSaveTaskSnapshot:
    """Tests for save_task_snapshot method with upsert logic."""

    async def test_save_task_snapshot_creates_new(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test creating new artifacts when none exist."""
        session_id = uuid4()
        task_id = uuid4()
        milestone_id = uuid4()

        artifacts_data = [
            {
                "artifact_type": "code",
                "filename": "main.py",
                "kind": "py",
                "content": "print('hello')",
                "path": "src",
                "sequence_number": 0,
            },
            {
                "artifact_type": "code",
                "filename": "utils.py",
                "kind": "py",
                "content": "def helper(): pass",
                "path": "src",
                "sequence_number": 1,
            },
        ]

        # Mock: batch query returns no existing artifacts
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repo.save_task_snapshot(
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            artifacts=artifacts_data,
        )

        # Should add each new artifact
        assert mock_session.add.call_count == 2
        mock_session.flush.assert_called_once()
        assert mock_session.refresh.call_count == 2
        assert len(result) == 2

    async def test_save_task_snapshot_updates_existing(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test updating existing artifact with same path/filename."""
        session_id = uuid4()
        task_id = uuid4()
        milestone_id = uuid4()

        # Existing artifact
        existing_artifact = _create_mock_artifact(
            session_id, "main.py", "old content", task_id=task_id, path="src"
        )

        artifacts_data = [
            {
                "artifact_type": "code",
                "filename": "main.py",
                "kind": "py",
                "content": "new content",
                "path": "src",
                "sequence_number": 0,
            },
        ]

        # Mock: batch query returns existing artifact
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [existing_artifact]
        mock_session.execute.return_value = mock_result

        result = await repo.save_task_snapshot(
            session_id=session_id,
            task_id=task_id,
            milestone_id=milestone_id,
            artifacts=artifacts_data,
        )

        # Should NOT add new artifact, just update existing
        mock_session.add.assert_not_called()
        # Existing artifact should be updated
        assert existing_artifact.content == "new content"
        assert existing_artifact.milestone_id == milestone_id
        assert len(result) == 1

    async def test_save_task_snapshot_empty(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test saving an empty snapshot."""
        session_id = uuid4()
        task_id = uuid4()

        result = await repo.save_task_snapshot(
            session_id=session_id,
            task_id=task_id,
            milestone_id=None,
            artifacts=[],
        )

        mock_session.add.assert_not_called()
        mock_session.flush.assert_not_called()  # No flush for empty artifacts
        assert result == []

    async def test_save_task_snapshot_defaults(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test snapshot with default values for new artifact."""
        session_id = uuid4()
        task_id = uuid4()

        artifacts_data = [
            {
                "filename": "index.html",
                "kind": "html",
                "content": "<html></html>",
            },
        ]

        # Mock: batch query returns no existing artifacts
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await repo.save_task_snapshot(
            session_id=session_id,
            task_id=task_id,
            milestone_id=None,
            artifacts=artifacts_data,
        )

        # Verify artifact was added with defaults
        added_artifact = mock_session.add.call_args[0][0]
        assert added_artifact.artifact_type == "code"  # default
        assert added_artifact.path == ""  # default
        assert added_artifact.sequence_number == 0  # default from index


class TestGetBySessionId:
    """Tests for get_by_session_id method (alias for get_latest_snapshot)."""

    async def test_get_by_session_id_returns_latest_snapshot(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test that get_by_session_id returns latest snapshot."""
        session_id = uuid4()
        task_id = uuid4()
        artifact = _create_mock_artifact(session_id, "main.py", "content", task_id=task_id)

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [artifact]

        mock_session.execute.side_effect = [mock_task_result, mock_artifacts_result]

        result = await repo.get_by_session_id(session_id)

        assert len(result) == 1
        assert result[0].filename == "main.py"

    async def test_get_by_session_id_with_limit(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test get_by_session_id respects limit parameter."""
        session_id = uuid4()
        task_id = uuid4()
        artifacts = [
            _create_mock_artifact(session_id, f"file{i}.py", f"content{i}", task_id=task_id)
            for i in range(10)
        ]

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = artifacts

        mock_session.execute.side_effect = [mock_task_result, mock_artifacts_result]

        result = await repo.get_by_session_id(session_id, limit=5)

        # Should return only first 5
        assert len(result) == 5


class TestGetByMilestoneId:
    """Tests for get_by_milestone_id method."""

    async def test_get_by_milestone_id_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting artifacts by milestone ID."""
        session_id = uuid4()
        task_id = uuid4()
        milestone_id = uuid4()
        artifact = _create_mock_artifact(
            session_id, "main.py", "content", task_id=task_id, milestone_id=milestone_id
        )

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


class TestGetCodeArtifacts:
    """Tests for get_code_artifacts method."""

    async def test_get_code_artifacts_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting only code artifacts from latest snapshot."""
        session_id = uuid4()
        task_id = uuid4()
        code_artifact = _create_mock_artifact(
            session_id, "main.py", "print('hello')", artifact_type="code", task_id=task_id
        )

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [code_artifact]

        mock_session.execute.side_effect = [mock_task_result, mock_artifacts_result]

        result = await repo.get_code_artifacts(session_id)

        assert len(result) == 1
        assert result[0].artifact_type == "code"

    async def test_get_code_artifacts_filters_non_code(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test that non-code artifacts are filtered out."""
        session_id = uuid4()
        task_id = uuid4()
        code_artifact = _create_mock_artifact(
            session_id, "main.py", "print('hello')", artifact_type="code", task_id=task_id
        )
        doc_artifact = _create_mock_artifact(
            session_id, "README.md", "# Docs", artifact_type="document", task_id=task_id
        )

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [code_artifact, doc_artifact]

        mock_session.execute.side_effect = [mock_task_result, mock_artifacts_result]

        result = await repo.get_code_artifacts(session_id)

        assert len(result) == 1
        assert result[0].artifact_type == "code"


class TestGetArtifactCount:
    """Tests for get_artifact_count method."""

    async def test_get_artifact_count(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test counting artifacts in latest snapshot."""
        session_id = uuid4()
        task_id = uuid4()
        artifacts = [
            _create_mock_artifact(session_id, f"file{i}.py", f"content{i}", task_id=task_id)
            for i in range(5)
        ]

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = artifacts

        mock_session.execute.side_effect = [mock_task_result, mock_artifacts_result]

        count = await repo.get_artifact_count(session_id)

        assert count == 5


class TestGetAllSessionArtifacts:
    """Tests for get_all_session_artifacts method."""

    async def test_get_all_session_artifacts_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test getting all artifacts from all tasks in session."""
        session_id = uuid4()
        task_id1 = uuid4()
        task_id2 = uuid4()
        artifact1 = _create_mock_artifact(session_id, "file1.py", "content1", task_id=task_id1)
        artifact2 = _create_mock_artifact(session_id, "file2.py", "content2", task_id=task_id2)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [artifact1, artifact2]
        mock_session.execute.return_value = mock_result

        result = await repo.get_all_session_artifacts(session_id)

        assert len(result) == 2
        assert result[0].filename == "file1.py"
        assert result[1].filename == "file2.py"


class TestDeleteByPaths:
    """Tests for delete_by_paths method."""

    async def test_delete_by_paths_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test deleting artifacts by their paths."""
        task_id = uuid4()
        paths_to_delete = ["src/old.py", "temp.txt"]

        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_session.execute.return_value = mock_result

        count = await repo.delete_by_paths(task_id, paths_to_delete)

        assert count == 2
        mock_session.execute.assert_called_once()

    async def test_delete_by_paths_empty_list(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test deleting with empty paths list returns 0."""
        task_id = uuid4()

        count = await repo.delete_by_paths(task_id, [])

        assert count == 0
        mock_session.execute.assert_not_called()

    async def test_delete_by_paths_no_directory(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test deleting file without directory path."""
        task_id = uuid4()
        paths = ["rootfile.txt"]

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        count = await repo.delete_by_paths(task_id, paths)

        assert count == 1


class TestGetExistingArtifactsMap:
    """Tests for _get_existing_artifacts_map method (batch query helper)."""

    async def test_get_existing_map_success(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test batch query for existing artifacts."""
        session_id = uuid4()
        task_id = uuid4()
        existing = _create_mock_artifact(
            session_id, "main.py", "old content", task_id=task_id, path="src"
        )

        artifacts_data = [
            {"path": "src", "filename": "main.py"},
            {"path": "src", "filename": "new.py"},
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [existing]
        mock_session.execute.return_value = mock_result

        result = await repo._get_existing_artifacts_map(task_id, artifacts_data)

        assert "src/main.py" in result
        assert "src/new.py" not in result
        assert result["src/main.py"].content == "old content"

    async def test_get_existing_map_empty_artifacts(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test with empty artifacts list returns empty dict."""
        task_id = uuid4()

        result = await repo._get_existing_artifacts_map(task_id, [])

        assert result == {}
        mock_session.execute.assert_not_called()

    async def test_get_existing_map_handles_empty_path(
        self,
        repo: ArtifactRepository,
        mock_session: AsyncMock,
    ):
        """Test handling artifacts with no path (root level)."""
        session_id = uuid4()
        task_id = uuid4()
        existing = _create_mock_artifact(session_id, "README.md", "docs", task_id=task_id, path="")

        artifacts_data = [
            {"filename": "README.md"},  # no path key
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [existing]
        mock_session.execute.return_value = mock_result

        result = await repo._get_existing_artifacts_map(task_id, artifacts_data)

        assert "/README.md" in result
