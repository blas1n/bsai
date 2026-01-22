"""Tests for artifacts router endpoints."""

import io
import zipfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from agent.api.auth import get_current_user_id
from agent.api.dependencies import get_db
from agent.api.handlers import register_exception_handlers
from agent.api.routers.artifacts import router


def _create_mock_session(user_id: str, **kwargs) -> MagicMock:
    """Create a mock session."""
    mock = MagicMock()
    mock.id = kwargs.get("id", uuid4())
    mock.user_id = user_id
    mock.title = kwargs.get("title", "Test Session")
    return mock


def _create_mock_artifact(
    session_id,
    task_id,
    filename: str,
    content: str,
    artifact_type: str = "code",
    kind: str = "py",
    path: str = "",
    sequence_number: int = 0,
    **kwargs,
) -> MagicMock:
    """Create a mock artifact with required fields."""
    mock = MagicMock()
    mock.id = kwargs.get("id", uuid4())
    mock.session_id = session_id
    mock.task_id = task_id
    mock.milestone_id = kwargs.get("milestone_id")
    mock.artifact_type = artifact_type
    mock.filename = filename
    mock.kind = kind
    mock.language = kwargs.get("language", "python")
    mock.content = content
    mock.path = path
    mock.sequence_number = sequence_number
    mock.created_at = kwargs.get("created_at", datetime.now(UTC))
    mock.updated_at = kwargs.get("updated_at", datetime.now(UTC))
    return mock


@pytest.fixture
def db_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    session.execute = AsyncMock(return_value=mock_result)

    return session


@pytest.fixture
def user_id() -> str:
    """Generate test user ID."""
    return "test-user-123"


@pytest.fixture
def app(db_session: AsyncMock, user_id: str) -> FastAPI:
    """Create test FastAPI app."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    async def override_get_db():
        yield db_session

    async def override_get_user_id():
        return user_id

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_user_id

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestListArtifacts:
    """Test GET /sessions/{session_id}/artifacts endpoint."""

    def test_list_artifacts_success(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test listing artifacts for a session (latest snapshot)."""
        session_id = uuid4()
        task_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)
        artifact1 = _create_mock_artifact(
            session_id, task_id, "main.py", "print('hello')", sequence_number=0
        )
        artifact2 = _create_mock_artifact(
            session_id, task_id, "utils.py", "def helper(): pass", sequence_number=1
        )

        # Mock session lookup
        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        # Mock latest task lookup (for get_latest_snapshot)
        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        # Mock artifacts lookup
        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [artifact1, artifact2]

        db_session.execute = AsyncMock(
            side_effect=[mock_session_result, mock_task_result, mock_artifacts_result]
        )

        response = client.get(f"/sessions/{session_id}/artifacts")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["filename"] == "main.py"
        assert data["items"][1]["filename"] == "utils.py"

    def test_list_artifacts_pagination(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test artifacts pagination."""
        session_id = uuid4()
        task_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)
        artifacts = [
            _create_mock_artifact(
                session_id, task_id, f"file{i}.py", f"content{i}", sequence_number=i
            )
            for i in range(5)
        ]

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = artifacts

        db_session.execute = AsyncMock(
            side_effect=[mock_session_result, mock_task_result, mock_artifacts_result]
        )

        response = client.get(
            f"/sessions/{session_id}/artifacts",
            params={"limit": 2, "offset": 1},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 1
        assert data["has_more"] is True

    def test_list_artifacts_session_not_found(
        self,
        client: TestClient,
        db_session: AsyncMock,
    ):
        """Test listing artifacts for non-existent session."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"/sessions/{session_id}/artifacts")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_artifacts_wrong_user(
        self,
        client: TestClient,
        db_session: AsyncMock,
    ):
        """Test listing artifacts for another user's session."""
        session_id = uuid4()

        mock_session = _create_mock_session("other-user", id=session_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"/sessions/{session_id}/artifacts")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_artifacts_with_task_id(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test listing artifacts for a specific task snapshot."""
        session_id = uuid4()
        task_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)
        artifact = _create_mock_artifact(
            session_id, task_id, "main.py", "print('hello')", sequence_number=0
        )

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        # When task_id is provided, get_by_task_id is called directly
        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [artifact]

        db_session.execute = AsyncMock(side_effect=[mock_session_result, mock_artifacts_result])

        response = client.get(f"/sessions/{session_id}/artifacts", params={"task_id": str(task_id)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["filename"] == "main.py"


class TestGetArtifact:
    """Test GET /sessions/{session_id}/artifacts/{artifact_id} endpoint."""

    def test_get_artifact_success(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test getting a specific artifact."""
        session_id = uuid4()
        task_id = uuid4()
        artifact_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)
        artifact = _create_mock_artifact(
            session_id, task_id, "main.py", "print('hello')", id=artifact_id
        )

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        mock_artifact_result = MagicMock()
        mock_artifact_result.scalar_one_or_none.return_value = artifact

        db_session.execute = AsyncMock(side_effect=[mock_session_result, mock_artifact_result])

        response = client.get(f"/sessions/{session_id}/artifacts/{artifact_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(artifact_id)
        assert data["filename"] == "main.py"
        assert data["content"] == "print('hello')"

    def test_get_artifact_not_found(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test getting non-existent artifact."""
        session_id = uuid4()
        artifact_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        mock_artifact_result = MagicMock()
        mock_artifact_result.scalar_one_or_none.return_value = None

        db_session.execute = AsyncMock(side_effect=[mock_session_result, mock_artifact_result])

        response = client.get(f"/sessions/{session_id}/artifacts/{artifact_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_artifact_wrong_session(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test getting artifact from wrong session."""
        session_id = uuid4()
        other_session_id = uuid4()
        task_id = uuid4()
        artifact_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)
        # Artifact belongs to different session
        artifact = _create_mock_artifact(
            other_session_id, task_id, "main.py", "content", id=artifact_id
        )

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        mock_artifact_result = MagicMock()
        mock_artifact_result.scalar_one_or_none.return_value = artifact

        db_session.execute = AsyncMock(side_effect=[mock_session_result, mock_artifact_result])

        response = client.get(f"/sessions/{session_id}/artifacts/{artifact_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDownloadArtifactsZip:
    """Test GET /sessions/{session_id}/artifacts/download/zip endpoint."""

    def test_download_zip_success(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test downloading artifacts as ZIP."""
        session_id = uuid4()
        task_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)
        artifact1 = _create_mock_artifact(
            session_id, task_id, "main.py", "print('hello')", path="src"
        )
        artifact2 = _create_mock_artifact(
            session_id, task_id, "utils.py", "def helper(): pass", path="src/utils"
        )

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [artifact1, artifact2]

        db_session.execute = AsyncMock(
            side_effect=[mock_session_result, mock_task_result, mock_artifacts_result]
        )

        response = client.get(f"/sessions/{session_id}/artifacts/download/zip")

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]
        # Check filename includes task_id
        assert str(task_id)[:8] in response.headers["content-disposition"]

        # Verify ZIP contents
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
            assert len(file_list) == 2
            assert "src/main.py" in file_list
            assert "src/utils/utils.py" in file_list

    def test_download_zip_no_path(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test downloading artifacts without paths."""
        session_id = uuid4()
        task_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)
        artifact = _create_mock_artifact(session_id, task_id, "main.py", "print('hello')", path="")

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [artifact]

        db_session.execute = AsyncMock(
            side_effect=[mock_session_result, mock_task_result, mock_artifacts_result]
        )

        response = client.get(f"/sessions/{session_id}/artifacts/download/zip")

        assert response.status_code == status.HTTP_200_OK

        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
            assert "main.py" in file_list

    def test_download_zip_duplicate_filenames(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test downloading ZIP handles duplicate filenames."""
        session_id = uuid4()
        task_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)
        artifact1 = _create_mock_artifact(session_id, task_id, "main.py", "content1", path="")
        artifact2 = _create_mock_artifact(session_id, task_id, "main.py", "content2", path="")

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [artifact1, artifact2]

        db_session.execute = AsyncMock(
            side_effect=[mock_session_result, mock_task_result, mock_artifacts_result]
        )

        response = client.get(f"/sessions/{session_id}/artifacts/download/zip")

        assert response.status_code == status.HTTP_200_OK

        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
            # With snapshot system, duplicates shouldn't happen but ZIP handles them
            assert len(file_list) >= 1

    def test_download_zip_no_artifacts(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test downloading ZIP when no artifacts exist."""
        session_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        # No completed task found
        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = None

        db_session.execute = AsyncMock(side_effect=[mock_session_result, mock_task_result])

        response = client.get(f"/sessions/{session_id}/artifacts/download/zip")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_download_zip_session_not_found(
        self,
        client: TestClient,
        db_session: AsyncMock,
    ):
        """Test downloading ZIP for non-existent session."""
        session_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"/sessions/{session_id}/artifacts/download/zip")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_download_zip_wrong_user(
        self,
        client: TestClient,
        db_session: AsyncMock,
    ):
        """Test downloading ZIP for another user's session."""
        session_id = uuid4()

        mock_session = _create_mock_session("other-user", id=session_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        db_session.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"/sessions/{session_id}/artifacts/download/zip")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_download_zip_path_with_filename(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test downloading ZIP when path already contains filename."""
        session_id = uuid4()
        task_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)
        # Path ends with the filename
        artifact = _create_mock_artifact(
            session_id, task_id, "main.py", "content", path="src/main.py"
        )

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [artifact]

        db_session.execute = AsyncMock(
            side_effect=[mock_session_result, mock_task_result, mock_artifacts_result]
        )

        response = client.get(f"/sessions/{session_id}/artifacts/download/zip")

        assert response.status_code == status.HTTP_200_OK

        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
            # Should not duplicate filename
            assert "src/main.py" in file_list

    def test_download_zip_leading_slash_path(
        self,
        client: TestClient,
        db_session: AsyncMock,
        user_id: str,
    ):
        """Test downloading ZIP with leading slash in path."""
        session_id = uuid4()
        task_id = uuid4()

        mock_session = _create_mock_session(user_id, id=session_id)
        artifact = _create_mock_artifact(session_id, task_id, "main.py", "content", path="/src")

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_session

        mock_task_result = MagicMock()
        mock_task_result.scalar_one_or_none.return_value = task_id

        mock_artifacts_result = MagicMock()
        mock_artifacts_result.scalars.return_value.all.return_value = [artifact]

        db_session.execute = AsyncMock(
            side_effect=[mock_session_result, mock_task_result, mock_artifacts_result]
        )

        response = client.get(f"/sessions/{session_id}/artifacts/download/zip")

        assert response.status_code == status.HTTP_200_OK

        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
            # Leading slash should be stripped
            assert "src/main.py" in file_list
