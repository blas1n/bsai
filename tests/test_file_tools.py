"""Tests for file manipulation tools."""

from src.agent.tools.file import list_directory, read_file, write_file


class TestReadFile:
    """Tests for read_file tool."""

    def test_read_existing_file(self, tmp_path):
        """Test reading an existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = read_file.invoke({"path": str(test_file)})

        assert result == "Hello, World!"

    def test_read_nonexistent_file(self):
        """Test reading a file that doesn't exist."""
        result = read_file.invoke({"path": "/nonexistent/path/file.txt"})

        assert "Error: File not found" in result

    def test_read_file_with_unicode(self, tmp_path):
        """Test reading a file with unicode content."""
        test_file = tmp_path / "unicode.txt"
        test_file.write_text("Hello 世界 🌍", encoding="utf-8")

        result = read_file.invoke({"path": str(test_file)})

        assert result == "Hello 世界 🌍"


class TestWriteFile:
    """Tests for write_file tool."""

    def test_write_new_file(self, tmp_path):
        """Test writing to a new file."""
        test_file = tmp_path / "new_file.txt"

        result = write_file.invoke({"path": str(test_file), "content": "Test content"})

        assert "Successfully wrote" in result
        assert test_file.read_text() == "Test content"

    def test_overwrite_existing_file(self, tmp_path):
        """Test overwriting an existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("Original content")

        result = write_file.invoke({"path": str(test_file), "content": "New content"})

        assert "Successfully wrote" in result
        assert test_file.read_text() == "New content"

    def test_write_to_invalid_path(self):
        """Test writing to an invalid path."""
        result = write_file.invoke(
            {"path": "/nonexistent/directory/file.txt", "content": "Test"}
        )

        assert "Error writing file" in result


class TestListDirectory:
    """Tests for list_directory tool."""

    def test_list_directory_with_files(self, tmp_path):
        """Test listing a directory with files."""
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.txt").touch()
        (tmp_path / "subdir").mkdir()

        result = list_directory.invoke({"path": str(tmp_path)})

        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "subdir" in result

    def test_list_empty_directory(self, tmp_path):
        """Test listing an empty directory."""
        result = list_directory.invoke({"path": str(tmp_path)})

        assert result == ""

    def test_list_nonexistent_directory(self):
        """Test listing a directory that doesn't exist."""
        result = list_directory.invoke({"path": "/nonexistent/directory"})

        assert "Error: Directory not found" in result

    def test_list_directory_sorted(self, tmp_path):
        """Test that directory listing is sorted."""
        (tmp_path / "zebra.txt").touch()
        (tmp_path / "alpha.txt").touch()
        (tmp_path / "beta.txt").touch()

        result = list_directory.invoke({"path": str(tmp_path)})
        lines = result.split("\n")

        assert lines == ["alpha.txt", "beta.txt", "zebra.txt"]
