"""Prompt Manager for loading and rendering prompts from YAML templates.

Manages prompt templates stored in YAML files and renders them using Mako.
"""

from enum import Enum
from pathlib import Path
from typing import Any

import structlog
import yaml
from mako.template import Template

logger = structlog.get_logger()


class PromptManager:
    """Manager for loading and rendering prompt templates.

    Loads YAML prompt files and renders them using Mako template engine.
    Supports caching for performance and common Mako macros.
    """

    def __init__(self, prompts_dir: Path | None = None) -> None:
        """Initialize PromptManager.

        Args:
            prompts_dir: Directory containing prompt YAML files.
                        Defaults to src/bsai/prompts/
        """
        if prompts_dir is None:
            # Default to prompts directory next to this file
            prompts_dir = Path(__file__).parent

        self.prompts_dir = prompts_dir
        self._cache: dict[str, dict[str, Any]] = {}
        self._template_cache: dict[str, Template] = {}
        self._macros: str | None = None

    def _load_macros(self) -> str:
        """Load common Mako macros from _macros.yaml.

        Returns:
            Combined macro definitions as a string, or empty string if not found.
        """
        if self._macros is not None:
            return self._macros

        macros_path = self.prompts_dir / "_macros.yaml"
        if not macros_path.exists():
            self._macros = ""
            return self._macros

        try:
            with open(macros_path, encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f)
                # Combine all macro definitions
                self._macros = "\n".join(str(v) for v in data.values() if isinstance(v, str))
                return self._macros
        except yaml.YAMLError as e:
            logger.warning("macros_load_error", path=str(macros_path), error=str(e))
            self._macros = ""
            return self._macros

    def _load_yaml(self, agent_name: str) -> dict[str, Any]:
        """Load YAML file for given agent.

        Args:
            agent_name: Name of the agent (e.g., 'conductor', 'qa_agent')

        Returns:
            Parsed YAML content as dictionary

        Raises:
            FileNotFoundError: If YAML file doesn't exist
            yaml.YAMLError: If YAML parsing fails
        """
        if agent_name in self._cache:
            return self._cache[agent_name]

        yaml_path = self.prompts_dir / f"{agent_name}.yaml"

        if not yaml_path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {yaml_path}. "
                f"Available files: {list(self.prompts_dir.glob('*.yaml'))}"
            )

        try:
            with open(yaml_path, encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f)
                self._cache[agent_name] = data
                return data
        except yaml.YAMLError as e:
            logger.error(
                "yaml_parse_error",
                agent=agent_name,
                path=str(yaml_path),
                error=str(e),
            )
            raise

    def _get_template(
        self, template_str: str, cache_key: str, include_macros: bool = True
    ) -> Template:
        """Get Mako template, using cache if available.

        Args:
            template_str: Template string
            cache_key: Unique key for caching
            include_macros: Whether to prepend common macros (default True)

        Returns:
            Compiled Mako template
        """
        if cache_key in self._template_cache:
            return self._template_cache[cache_key]

        # Prepend macros if requested
        if include_macros:
            macros = self._load_macros()
            full_template = f"{macros}\n{template_str}" if macros else template_str
        else:
            full_template = template_str

        template = Template(text=full_template, strict_undefined=True)
        self._template_cache[cache_key] = template
        return template

    def render(
        self,
        agent_name: str,
        prompt_key: Enum,
        **kwargs: Any,
    ) -> str:
        """Render prompt template with given variables.

        Args:
            agent_name: Name of the agent (e.g., 'conductor', 'qa_agent')
            prompt_key: Key of the prompt in YAML (Enum from prompts.keys)
            **kwargs: Template variables to render

        Returns:
            Rendered prompt string

        Raises:
            FileNotFoundError: If agent YAML file doesn't exist
            KeyError: If prompt_key doesn't exist in YAML
            ValueError: If template rendering fails

        Example:
            >>> from bsai.prompts.keys import ArchitectPrompts
            >>> manager = PromptManager()
            >>> prompt = manager.render(
            ...     "architect",
            ...     ArchitectPrompts.PLANNING_PROMPT,
            ...     original_request="Build a web scraper"
            ... )
        """
        # Convert enum to string
        key_str = prompt_key.value

        # Load YAML data
        data = self._load_yaml(agent_name)

        # Get template string
        if key_str not in data:
            raise KeyError(
                f"Prompt key '{key_str}' not found in {agent_name}.yaml. "
                f"Available keys: {list(data.keys())}"
            )

        template_str = data[key_str]
        if not isinstance(template_str, str):
            raise ValueError(
                f"Prompt '{prompt_key}' in {agent_name}.yaml must be a string, "
                f"got {type(template_str)}"
            )

        # Render template
        cache_key = f"{agent_name}:{key_str}"
        template = self._get_template(template_str, cache_key)

        try:
            rendered = str(template.render(**kwargs))
            return rendered.strip()
        except Exception as e:
            logger.error(
                "template_render_error",
                agent=agent_name,
                prompt_key=prompt_key,
                error=str(e),
                variables=list(kwargs.keys()),
            )
            raise ValueError(f"Failed to render template: {e}") from e

    def get_data(self, agent_name: str, key: Enum) -> Any:
        """Get raw data from YAML without rendering.

        Useful for accessing non-template data like strategy mappings.

        Args:
            agent_name: Name of the agent
            key: Key in the YAML file (Enum from prompts.keys)

        Returns:
            Raw data from YAML

        Raises:
            FileNotFoundError: If agent YAML file doesn't exist
            KeyError: If key doesn't exist in YAML

        Example:
            >>> from bsai.prompts.keys import WorkerPrompts
            >>> manager = PromptManager()
            >>> data = manager.get_data("worker", WorkerPrompts.SYSTEM_PROMPT)
        """
        # Convert enum to string
        key_str = key.value

        data = self._load_yaml(agent_name)

        if key_str not in data:
            raise KeyError(
                f"Key '{key_str}' not found in {agent_name}.yaml. "
                f"Available keys: {list(data.keys())}"
            )

        return data[key_str]

    def render_template(
        self,
        template_str: str,
        cache_key: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Render a template string directly with Mako.

        Useful for rendering sub-templates that are retrieved via get_data().

        Args:
            template_str: Template string to render
            cache_key: Optional cache key (if None, no caching)
            **kwargs: Template variables

        Returns:
            Rendered template string

        Raises:
            ValueError: If template rendering fails

        Example:
            >>> manager = PromptManager()
            >>> retry_template = manager.get_data("qa_agent", "retry_context_template")
            >>> rendered = manager.render_template(
            ...     retry_template,
            ...     cache_key="qa_agent:retry_context",
            ...     attempt_number=2,
            ...     max_retries=3
            ... )
        """
        if cache_key and cache_key in self._template_cache:
            template = self._template_cache[cache_key]
        else:
            template = Template(text=template_str, strict_undefined=True)
            if cache_key:
                self._template_cache[cache_key] = template

        try:
            rendered = str(template.render(**kwargs))
            return rendered.strip()
        except Exception as e:
            logger.error(
                "template_render_error",
                cache_key=cache_key,
                error=str(e),
                variables=list(kwargs.keys()),
            )
            raise ValueError(f"Failed to render template: {e}") from e

    def clear_cache(self) -> None:
        """Clear all caches.

        Useful in development when YAML files are modified.
        """
        self._cache.clear()
        self._template_cache.clear()
        self._macros = None
        logger.debug("prompt_cache_cleared")
