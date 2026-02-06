"""Artifact extraction utilities.

Extracts file artifacts from structured LLM output.
"""

from dataclasses import dataclass

import structlog

from bsai.llm.schemas import WorkerOutput

logger = structlog.get_logger()


@dataclass
class ExtractedArtifact:
    """Represents an extracted artifact from text."""

    artifact_type: str  # 'code', 'file', 'document'
    filename: str
    kind: str
    content: str
    path: str
    sequence_number: int = 0


@dataclass
class ExtractionResult:
    """Result of artifact extraction including deletions."""

    artifacts: list[ExtractedArtifact]
    deleted_paths: list[str]


def extract_artifacts(response_content: str) -> ExtractionResult:
    """Extract file artifacts and deletion requests from structured Worker output.

    Parses the WorkerOutput JSON and extracts file artifacts and deleted file paths.

    Args:
        response_content: JSON string from Worker LLM response

    Returns:
        ExtractionResult with artifacts and deleted_paths (empty if parsing fails)
    """
    try:
        output = WorkerOutput.model_validate_json(response_content)
    except Exception as e:
        logger.warning(
            "artifact_extraction_failed",
            error=str(e),
            content_length=len(response_content),
            content_preview=response_content[:200] if response_content else "",
        )
        return ExtractionResult(artifacts=[], deleted_paths=[])

    artifacts: list[ExtractedArtifact] = []

    for idx, file in enumerate(output.files):
        # Split path into directory and filename
        if "/" in file.path:
            path, filename = file.path.rsplit("/", 1)
        else:
            path = ""
            filename = file.path

        artifact = ExtractedArtifact(
            artifact_type="file",
            filename=filename,
            kind=file.kind,
            content=file.content,
            path=path,
            sequence_number=idx,
        )
        artifacts.append(artifact)

    return ExtractionResult(
        artifacts=artifacts,
        deleted_paths=output.deleted_files,
    )


def get_explanation(response_content: str) -> str:
    """Extract explanation from structured Worker output.

    Args:
        response_content: JSON string from Worker LLM response

    Returns:
        Explanation text for the user (raw content if parsing fails)
    """
    try:
        output = WorkerOutput.model_validate_json(response_content)
        return output.explanation
    except Exception as e:
        logger.warning(
            "explanation_extraction_failed",
            error=str(e),
            content_length=len(response_content),
        )
        # Return raw content if JSON parsing fails
        return response_content
