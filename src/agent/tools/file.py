"""File manipulation tools for the code agent."""

import os

from langchain_core.tools import tool


@tool
def read_file(path: str) -> str:
    """Read and return the content of a file at the given path.

    Args:
        path: Path to the file to read

    Returns:
        The file content as a string
    """
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file at the given path.

    Args:
        path: Path to the file to write
        content: Content to write to the file

    Returns:
        Success message or error description
    """
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool
def list_directory(path: str = ".") -> str:
    """List files and directories in the given path.

    Args:
        path: Directory path to list (defaults to current directory)

    Returns:
        Newline-separated list of files and directories
    """
    try:
        entries = os.listdir(path)
        return "\n".join(sorted(entries))
    except FileNotFoundError:
        return f"Error: Directory not found: {path}"
    except Exception as e:
        return f"Error listing directory: {e}"
