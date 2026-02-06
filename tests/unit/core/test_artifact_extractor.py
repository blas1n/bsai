"""Tests for artifact extraction utilities.

Note: Task-level snapshot system with explicit delete support.
- Worker output `files` array contains created/modified files
- Worker output `deleted_files` array contains paths to delete
"""

import json

from bsai.core.artifact_extractor import (
    ExtractedArtifact,
    ExtractionResult,
    extract_artifacts,
    get_explanation,
)


class TestExtractedArtifact:
    """Tests for ExtractedArtifact dataclass."""

    def test_create_artifact(self):
        """Test creating an ExtractedArtifact."""
        artifact = ExtractedArtifact(
            artifact_type="code",
            filename="main.py",
            kind="py",
            content="print('hello')",
            path="src",
            sequence_number=0,
        )

        assert artifact.artifact_type == "code"
        assert artifact.filename == "main.py"
        assert artifact.kind == "py"
        assert artifact.content == "print('hello')"
        assert artifact.path == "src"
        assert artifact.sequence_number == 0

    def test_default_sequence_number(self):
        """Test default sequence number is 0."""
        artifact = ExtractedArtifact(
            artifact_type="file",
            filename="config.json",
            kind="json",
            content="{}",
            path="",
        )

        assert artifact.sequence_number == 0


class TestExtractArtifacts:
    """Tests for extract_artifacts function."""

    def test_extract_single_artifact(self):
        """Test extracting a single artifact."""
        content = json.dumps(
            {
                "explanation": "Created a Python file",
                "files": [
                    {
                        "path": "src/main.py",
                        "kind": "py",
                        "content": "print('hello')",
                    }
                ],
                "deleted_files": [],
            }
        )

        result = extract_artifacts(content)

        assert isinstance(result, ExtractionResult)
        assert len(result.artifacts) == 1
        assert result.artifacts[0].filename == "main.py"
        assert result.artifacts[0].path == "src"
        assert result.artifacts[0].kind == "py"
        assert result.artifacts[0].content == "print('hello')"
        assert result.artifacts[0].artifact_type == "file"
        assert result.artifacts[0].sequence_number == 0
        assert result.deleted_paths == []

    def test_extract_multiple_artifacts(self):
        """Test extracting multiple artifacts."""
        content = json.dumps(
            {
                "explanation": "Created multiple files",
                "files": [
                    {
                        "path": "src/main.py",
                        "kind": "py",
                        "content": "from utils import helper",
                    },
                    {
                        "path": "src/utils.py",
                        "kind": "py",
                        "content": "def helper(): pass",
                    },
                    {
                        "path": "config.json",
                        "kind": "json",
                        "content": '{"key": "value"}',
                    },
                ],
                "deleted_files": [],
            }
        )

        result = extract_artifacts(content)

        assert len(result.artifacts) == 3
        assert result.artifacts[0].filename == "main.py"
        assert result.artifacts[0].sequence_number == 0
        assert result.artifacts[1].filename == "utils.py"
        assert result.artifacts[1].sequence_number == 1
        assert result.artifacts[2].filename == "config.json"
        assert result.artifacts[2].sequence_number == 2

    def test_extract_artifact_no_path(self):
        """Test extracting artifact without directory path."""
        content = json.dumps(
            {
                "explanation": "Created a file in root",
                "files": [
                    {
                        "path": "README.md",
                        "kind": "md",
                        "content": "# Project",
                    }
                ],
                "deleted_files": [],
            }
        )

        result = extract_artifacts(content)

        assert len(result.artifacts) == 1
        assert result.artifacts[0].filename == "README.md"
        assert result.artifacts[0].path == ""

    def test_extract_empty_files_list(self):
        """Test extracting when files list is empty."""
        content = json.dumps(
            {
                "explanation": "No files generated",
                "files": [],
                "deleted_files": [],
            }
        )

        result = extract_artifacts(content)

        assert result.artifacts == []
        assert result.deleted_paths == []

    def test_extract_invalid_json(self):
        """Test extracting from invalid JSON returns empty result."""
        content = "This is not valid JSON"

        result = extract_artifacts(content)

        assert result.artifacts == []
        assert result.deleted_paths == []

    def test_extract_missing_files_key(self):
        """Test extracting when files key is missing."""
        content = json.dumps(
            {
                "explanation": "Missing files",
            }
        )

        result = extract_artifacts(content)

        assert result.artifacts == []
        assert result.deleted_paths == []

    def test_extract_nested_path(self):
        """Test extracting artifact with deeply nested path."""
        content = json.dumps(
            {
                "explanation": "Created nested file",
                "files": [
                    {
                        "path": "src/components/ui/Button.tsx",
                        "kind": "tsx",
                        "content": "export const Button = () => {}",
                    }
                ],
                "deleted_files": [],
            }
        )

        result = extract_artifacts(content)

        assert len(result.artifacts) == 1
        assert result.artifacts[0].filename == "Button.tsx"
        assert result.artifacts[0].path == "src/components/ui"

    def test_extract_empty_content(self):
        """Test extracting from empty content."""
        result = extract_artifacts("")

        assert result.artifacts == []
        assert result.deleted_paths == []

    def test_extract_with_deleted_files(self):
        """Test extracting artifacts with deleted_files array."""
        content = json.dumps(
            {
                "explanation": "Modified files and deleted old ones",
                "files": [
                    {
                        "path": "src/new.py",
                        "kind": "py",
                        "content": "# new file",
                    }
                ],
                "deleted_files": ["src/old.py", "temp.txt"],
            }
        )

        result = extract_artifacts(content)

        assert len(result.artifacts) == 1
        assert result.artifacts[0].filename == "new.py"
        assert result.deleted_paths == ["src/old.py", "temp.txt"]

    def test_extract_only_deletions(self):
        """Test extracting when only deleting files."""
        content = json.dumps(
            {
                "explanation": "Deleted unnecessary files",
                "files": [],
                "deleted_files": ["temp/cache.txt", "old_config.json"],
            }
        )

        result = extract_artifacts(content)

        assert result.artifacts == []
        assert result.deleted_paths == ["temp/cache.txt", "old_config.json"]


class TestGetExplanation:
    """Tests for get_explanation function."""

    def test_get_explanation_success(self):
        """Test getting explanation from valid JSON."""
        content = json.dumps(
            {
                "explanation": "This is the explanation text",
                "files": [],
                "deleted_files": [],
            }
        )

        result = get_explanation(content)

        assert result == "This is the explanation text"

    def test_get_explanation_with_files(self):
        """Test getting explanation when files are present."""
        content = json.dumps(
            {
                "explanation": "Created a Python file for you",
                "files": [
                    {
                        "path": "main.py",
                        "kind": "py",
                        "content": "print('hello')",
                    }
                ],
                "deleted_files": [],
            }
        )

        result = get_explanation(content)

        assert result == "Created a Python file for you"

    def test_get_explanation_invalid_json(self):
        """Test getting explanation from invalid JSON returns raw content."""
        content = "This is plain text, not JSON"

        result = get_explanation(content)

        assert result == content

    def test_get_explanation_missing_key(self):
        """Test getting explanation when key is missing returns raw content."""
        content = json.dumps(
            {
                "files": [],
            }
        )

        result = get_explanation(content)

        # Should return raw content since explanation is missing
        assert result == content

    def test_get_explanation_empty_content(self):
        """Test getting explanation from empty content."""
        result = get_explanation("")

        assert result == ""

    def test_get_explanation_multiline(self):
        """Test getting multiline explanation."""
        content = json.dumps(
            {
                "explanation": "Line 1\nLine 2\nLine 3",
                "files": [],
                "deleted_files": [],
            }
        )

        result = get_explanation(content)

        assert result == "Line 1\nLine 2\nLine 3"

    def test_get_explanation_unicode(self):
        """Test getting explanation with unicode characters."""
        content = json.dumps(
            {
                "explanation": "한글 설명입니다. 日本語の説明です。",
                "files": [],
                "deleted_files": [],
            }
        )

        result = get_explanation(content)

        assert result == "한글 설명입니다. 日本語の説明です。"


class TestSnapshotBehavior:
    """Tests verifying task-level snapshot behavior with explicit delete support.

    In the snapshot model:
    - Worker output `files` array = created/modified files
    - Worker output `deleted_files` array = files to delete
    - Unchanged files are automatically preserved by baseline copy
    """

    def test_extract_artifacts_with_explicit_delete(self):
        """Test that deleted_files explicitly marks files for removal."""
        # Task 1: Create files A, B, C
        task1_output = json.dumps(
            {
                "explanation": "Created initial files",
                "files": [
                    {"path": "A.py", "kind": "py", "content": "# A"},
                    {"path": "B.py", "kind": "py", "content": "# B"},
                    {"path": "C.py", "kind": "py", "content": "# C"},
                ],
                "deleted_files": [],
            }
        )

        task1_result = extract_artifacts(task1_output)
        assert len(task1_result.artifacts) == 3
        assert task1_result.deleted_paths == []

        # Task 2: Modify A, delete C explicitly
        # B is unchanged so not included in files array
        task2_output = json.dumps(
            {
                "explanation": "Modified A, deleted C",
                "files": [
                    {"path": "A.py", "kind": "py", "content": "# A modified"},
                ],
                "deleted_files": ["C.py"],
            }
        )

        task2_result = extract_artifacts(task2_output)
        assert len(task2_result.artifacts) == 1
        assert task2_result.artifacts[0].content == "# A modified"
        assert task2_result.deleted_paths == ["C.py"]

    def test_empty_files_with_deletions(self):
        """Test deleting files without creating new ones."""
        output = json.dumps(
            {
                "explanation": "Removed old files",
                "files": [],
                "deleted_files": ["old1.py", "old2.py"],
            }
        )

        result = extract_artifacts(output)
        assert result.artifacts == []
        assert result.deleted_paths == ["old1.py", "old2.py"]
