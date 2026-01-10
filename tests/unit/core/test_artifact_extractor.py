"""Tests for artifact extraction utilities."""

import json

from agent.core.artifact_extractor import (
    ExtractedArtifact,
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
            }
        )

        result = extract_artifacts(content)

        assert len(result) == 1
        assert result[0].filename == "main.py"
        assert result[0].path == "src"
        assert result[0].kind == "py"
        assert result[0].content == "print('hello')"
        assert result[0].artifact_type == "file"
        assert result[0].sequence_number == 0

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
            }
        )

        result = extract_artifacts(content)

        assert len(result) == 3
        assert result[0].filename == "main.py"
        assert result[0].sequence_number == 0
        assert result[1].filename == "utils.py"
        assert result[1].sequence_number == 1
        assert result[2].filename == "config.json"
        assert result[2].sequence_number == 2

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
            }
        )

        result = extract_artifacts(content)

        assert len(result) == 1
        assert result[0].filename == "README.md"
        assert result[0].path == ""

    def test_extract_empty_files_list(self):
        """Test extracting when files list is empty."""
        content = json.dumps(
            {
                "explanation": "No files generated",
                "files": [],
            }
        )

        result = extract_artifacts(content)

        assert result == []

    def test_extract_invalid_json(self):
        """Test extracting from invalid JSON returns empty list."""
        content = "This is not valid JSON"

        result = extract_artifacts(content)

        assert result == []

    def test_extract_missing_files_key(self):
        """Test extracting when files key is missing."""
        content = json.dumps(
            {
                "explanation": "Missing files",
            }
        )

        result = extract_artifacts(content)

        assert result == []

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
            }
        )

        result = extract_artifacts(content)

        assert len(result) == 1
        assert result[0].filename == "Button.tsx"
        assert result[0].path == "src/components/ui"

    def test_extract_empty_content(self):
        """Test extracting from empty content."""
        result = extract_artifacts("")

        assert result == []


class TestGetExplanation:
    """Tests for get_explanation function."""

    def test_get_explanation_success(self):
        """Test getting explanation from valid JSON."""
        content = json.dumps(
            {
                "explanation": "This is the explanation text",
                "files": [],
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
            }
        )

        result = get_explanation(content)

        assert result == "한글 설명입니다. 日本語の説明です。"
