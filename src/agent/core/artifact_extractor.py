"""Artifact extraction utilities.

Extracts file artifacts from structured LLM output.
"""

from dataclasses import dataclass

from agent.llm.schemas import WorkerOutput


@dataclass
class ExtractedArtifact:
    """Represents an extracted artifact from text."""

    artifact_type: str  # 'code', 'file', 'document'
    filename: str
    kind: str
    content: str
    path: str
    sequence_number: int = 0


def extract_artifacts(response_content: str) -> list[ExtractedArtifact]:
    """Extract file artifacts from structured Worker output.

    Parses the WorkerOutput JSON and extracts file artifacts.

    Args:
        response_content: JSON string from Worker LLM response

    Returns:
        List of extracted artifacts
    """
    output = WorkerOutput.model_validate_json(response_content)

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

    return artifacts


def get_explanation(response_content: str) -> str:
    """Extract explanation from structured Worker output.

    Args:
        response_content: JSON string from Worker LLM response

    Returns:
        Explanation text for the user
    """
    output = WorkerOutput.model_validate_json(response_content)
    return output.explanation
