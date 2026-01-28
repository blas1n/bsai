"""Prompt loading utilities."""

from pathlib import Path

import yaml

_prompts_cache: dict[str, str] | None = None


def load_prompts() -> dict[str, str]:
    """Load prompts from YAML file.

    Returns:
        Dictionary mapping prompt names to their content.
    """
    global _prompts_cache
    if _prompts_cache is not None:
        return _prompts_cache

    prompts_file = Path(__file__).parent / "prompts.yaml"
    with open(prompts_file) as f:
        data = yaml.safe_load(f)

    _prompts_cache = {key: value["content"].strip() for key, value in data.items()}
    return _prompts_cache


def get_prompt(name: str) -> str:
    """Get a specific prompt by name.

    Args:
        name: The prompt name (e.g., 'system', 'planner', 'executor', 'replanner')

    Returns:
        The prompt content string.

    Raises:
        KeyError: If the prompt name is not found.
    """
    prompts = load_prompts()
    return prompts[name]
