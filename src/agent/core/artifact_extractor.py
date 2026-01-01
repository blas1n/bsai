"""Artifact extraction utilities.

Extracts code blocks and other artifacts from LLM output text.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound


@dataclass
class ExtractedArtifact:
    """Represents an extracted artifact from text."""

    artifact_type: str  # 'code', 'file', 'document'
    filename: str
    language: str | None
    content: str
    path: str | None = None
    sequence_number: int = 0


@lru_cache(maxsize=128)
def _get_extension_for_language(language: str) -> str:
    """Get file extension for a programming language using pygments.

    Args:
        language: Programming language name

    Returns:
        File extension including dot (e.g., '.py'), or '.txt' if unknown.
        Returns empty string for languages without extensions (e.g., Dockerfile).
    """
    try:
        lexer = get_lexer_by_name(language.lower())
        if lexer.filenames:
            for pattern in lexer.filenames:
                if "*." in pattern:
                    return pattern.replace("*", "")
            return ""
        return ".txt"
    except ClassNotFound:
        return ".txt"


def extract_artifacts(text: str) -> list[ExtractedArtifact]:
    """Extract code blocks and artifacts from text.

    Parses markdown code blocks (```language ... ```) and extracts
    them as individual artifacts with filename and path detection.

    Args:
        text: Text content containing code blocks

    Returns:
        List of extracted artifacts
    """
    artifacts: list[ExtractedArtifact] = []

    # Regex to match code blocks: ```language\n...```
    # Captures: language (optional), content
    code_block_pattern = re.compile(
        r"```(\w+)?\s*\n([\s\S]*?)```",
        re.MULTILINE,
    )

    for idx, match in enumerate(code_block_pattern.finditer(text)):
        language = match.group(1) or "text"
        content = match.group(2).strip()

        if not content:
            continue

        # Extract path and filename from content
        path, filename = _extract_path_and_filename(content, language, idx)

        artifact = ExtractedArtifact(
            artifact_type="code",
            filename=filename,
            language=language.lower(),
            content=content,
            path=path,
            sequence_number=idx,
        )
        artifacts.append(artifact)

    return artifacts


def _extract_path_and_filename(content: str, language: str, index: int) -> tuple[str | None, str]:
    """Extract path and filename from content.

    Looks for path patterns in comments at the start of code:
    - // src/js/game.js
    - # src/utils/helper.py
    - /* src/css/styles.css */
    - <!-- src/index.html -->

    Args:
        content: Code content
        language: Programming language
        index: Artifact index for fallback naming

    Returns:
        Tuple of (path, filename). Path may be None if no path found.
    """
    # Patterns for path/filename detection (capture full path including filename)
    path_patterns = [
        # // path/to/file.ext or # path/to/file.ext at start
        r"^(?://|#)\s*([a-zA-Z0-9_\-./]+/[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        # // file: path/to/file.ext or # file: path/to/file.ext
        r"^(?://|#)\s*(?:file(?:name)?:?\s*)([a-zA-Z0-9_\-./]+/[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        # /* path/to/file.ext */ at start
        r"^/\*\s*([a-zA-Z0-9_\-./]+/[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\s*\*/",
        # <!-- path/to/file.ext --> at start
        r"^<!--\s*([a-zA-Z0-9_\-./]+/[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\s*-->",
    ]

    # Patterns for filename only (no path)
    filename_patterns = [
        # // filename.ext or # filename.ext at start
        r"^(?://|#)\s*([a-zA-Z0-9_\-.]+\.[a-zA-Z0-9]+)$",
        # // file: filename.ext or # file: filename.ext
        r"^(?://|#)\s*(?:file(?:name)?:?\s*)([a-zA-Z0-9_\-.]+\.[a-zA-Z0-9]+)$",
        # /* filename.ext */ at start
        r"^/\*\s*([a-zA-Z0-9_\-.]+\.[a-zA-Z0-9]+)\s*\*/$",
        # <!-- filename.ext --> at start
        r"^<!--\s*([a-zA-Z0-9_\-.]+\.[a-zA-Z0-9]+)\s*-->$",
    ]

    first_line = content.split("\n")[0].strip()

    # First try to match paths (with directories)
    for pattern in path_patterns:
        match = re.match(pattern, first_line, re.IGNORECASE)
        if match:
            full_path = match.group(1)
            # Split into directory and filename
            if "/" in full_path:
                parts = full_path.rsplit("/", 1)
                return parts[0], parts[1]
            return None, full_path

    # Then try to match filename only
    for pattern in filename_patterns:
        match = re.match(pattern, first_line, re.IGNORECASE)
        if match:
            return None, match.group(1)

    # Generate filename based on language
    return None, _generate_filename(language, index)


def _generate_filename(language: str, index: int) -> str:
    """Generate a default filename based on language.

    Args:
        language: Programming language
        index: Artifact index

    Returns:
        Generated filename
    """
    lang_lower = language.lower()

    # Special cases for common filenames
    if lang_lower == "html":
        return "index.html" if index == 0 else f"page_{index + 1}.html"
    if lang_lower in ("javascript", "js"):
        return "script.js" if index == 0 else f"script_{index + 1}.js"
    if lang_lower in ("typescript", "ts"):
        return "index.ts" if index == 0 else f"file_{index + 1}.ts"
    if lang_lower == "css":
        return "styles.css" if index == 0 else f"styles_{index + 1}.css"
    if lang_lower == "python":
        return "main.py" if index == 0 else f"module_{index + 1}.py"

    ext = _get_extension_for_language(lang_lower)

    # Base filename
    base = f"code_{index + 1}" if index > 0 else "code"

    return f"{base}{ext}"
