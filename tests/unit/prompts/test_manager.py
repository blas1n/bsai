"""Tests for PromptManager."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml

from agent.prompts.keys import ConductorPrompts, MetaPrompterPrompts
from agent.prompts.manager import PromptManager


@pytest.fixture
def temp_prompts_dir() -> Generator[Path, None, None]:
    """Create temporary directory with test prompts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prompts_dir = Path(tmpdir)

        # Create test YAML files
        conductor_prompts = {
            "analysis_prompt": "Analyze: ${original_request}",
        }
        (prompts_dir / "conductor.yaml").write_text(yaml.dump(conductor_prompts))

        meta_prompter_prompts = {
            "meta_prompt": "Task: ${task}\nComplexity: ${complexity}",
            "strategies": {
                "TRIVIAL": "Simple strategy",
                "MODERATE": "Moderate strategy",
            },
        }
        (prompts_dir / "meta_prompter.yaml").write_text(yaml.dump(meta_prompter_prompts))

        yield prompts_dir


@pytest.fixture
def prompt_manager(temp_prompts_dir: Path) -> PromptManager:
    """Create PromptManager with test prompts."""
    return PromptManager(prompts_dir=temp_prompts_dir)


class TestPromptManager:
    """Test PromptManager functionality."""

    def test_render_with_enum(self, prompt_manager: PromptManager) -> None:
        """Test rendering prompt with enum key."""
        result = prompt_manager.render(
            "conductor",
            ConductorPrompts.ANALYSIS_PROMPT,
            original_request="Build a web scraper",
        )

        assert result == "Analyze: Build a web scraper"

    def test_render_with_multiple_variables(self, prompt_manager: PromptManager) -> None:
        """Test rendering with multiple template variables."""
        result = prompt_manager.render(
            "meta_prompter",
            MetaPrompterPrompts.META_PROMPT,
            task="Write tests",
            complexity="MODERATE",
        )

        assert "Task: Write tests" in result
        assert "Complexity: MODERATE" in result

    def test_render_caching(self, prompt_manager: PromptManager) -> None:
        """Test that templates are cached."""
        # Render twice
        result1 = prompt_manager.render(
            "conductor",
            ConductorPrompts.ANALYSIS_PROMPT,
            original_request="Test 1",
        )
        result2 = prompt_manager.render(
            "conductor",
            ConductorPrompts.ANALYSIS_PROMPT,
            original_request="Test 2",
        )

        # Results should be different (different variables)
        assert result1 == "Analyze: Test 1"
        assert result2 == "Analyze: Test 2"

        # But cache should have the template
        assert "conductor:analysis_prompt" in prompt_manager._template_cache

    def test_render_missing_file_raises_error(self, prompt_manager: PromptManager) -> None:
        """Test error when YAML file doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Prompt file not found"):
            prompt_manager.render(
                "nonexistent",
                ConductorPrompts.ANALYSIS_PROMPT,
                test="value",
            )

    def test_render_missing_key_raises_error(self, prompt_manager: PromptManager) -> None:
        """Test error when prompt key doesn't exist."""
        # Create enum with wrong value
        from enum import Enum

        class FakePrompts(str, Enum):
            WRONG_KEY = "wrong_key"

        with pytest.raises(KeyError, match="not found"):
            prompt_manager.render("conductor", FakePrompts.WRONG_KEY, test="value")  # type: ignore

    def test_render_missing_variable_raises_error(self, prompt_manager: PromptManager) -> None:
        """Test error when template variable is missing."""
        with pytest.raises(ValueError, match="Failed to render template"):
            # Missing 'original_request' variable
            prompt_manager.render("conductor", ConductorPrompts.ANALYSIS_PROMPT)

    def test_get_data_with_enum(self, prompt_manager: PromptManager) -> None:
        """Test getting raw data with enum key."""
        strategies = prompt_manager.get_data("meta_prompter", MetaPrompterPrompts.STRATEGIES)

        assert isinstance(strategies, dict)
        assert "TRIVIAL" in strategies
        assert "MODERATE" in strategies
        assert strategies["TRIVIAL"] == "Simple strategy"

    def test_get_data_missing_key_raises_error(self, prompt_manager: PromptManager) -> None:
        """Test error when data key doesn't exist."""
        from enum import Enum

        class FakePrompts(str, Enum):
            WRONG_KEY = "wrong_key"

        with pytest.raises(KeyError, match="not found"):
            prompt_manager.get_data("conductor", FakePrompts.WRONG_KEY)  # type: ignore

    def test_render_template_direct(self, prompt_manager: PromptManager) -> None:
        """Test rendering template string directly."""
        template_str = "Hello, ${name}!"

        result = prompt_manager.render_template(template_str, name="World")

        assert result == "Hello, World!"

    def test_render_template_with_caching(self, prompt_manager: PromptManager) -> None:
        """Test template caching in render_template."""
        template_str = "Count: ${count}"

        result1 = prompt_manager.render_template(template_str, cache_key="test:count", count=1)
        result2 = prompt_manager.render_template(template_str, cache_key="test:count", count=2)

        assert result1 == "Count: 1"
        assert result2 == "Count: 2"
        assert "test:count" in prompt_manager._template_cache

    def test_render_template_without_caching(self, prompt_manager: PromptManager) -> None:
        """Test rendering without cache key."""
        template_str = "No cache: ${value}"

        result = prompt_manager.render_template(template_str, value="test")

        assert result == "No cache: test"
        # No cache key provided, so shouldn't be cached
        assert "no_cache" not in prompt_manager._template_cache

    def test_clear_cache(self, prompt_manager: PromptManager) -> None:
        """Test cache clearing."""
        # Load some data to populate cache
        prompt_manager.render(
            "conductor", ConductorPrompts.ANALYSIS_PROMPT, original_request="Test"
        )

        # Cache should have data
        assert len(prompt_manager._cache) > 0
        assert len(prompt_manager._template_cache) > 0

        # Clear cache
        prompt_manager.clear_cache()

        # Cache should be empty
        assert len(prompt_manager._cache) == 0
        assert len(prompt_manager._template_cache) == 0

    def test_yaml_parsing_error(self, temp_prompts_dir: Path) -> None:
        """Test handling of invalid YAML."""
        # Create invalid YAML file
        (temp_prompts_dir / "invalid.yaml").write_text("invalid: yaml: content:")

        manager = PromptManager(prompts_dir=temp_prompts_dir)

        with pytest.raises(yaml.YAMLError):
            manager.render("invalid", ConductorPrompts.ANALYSIS_PROMPT, test="value")

    def test_conditional_template(self, temp_prompts_dir: Path) -> None:
        """Test Mako conditional in template."""
        from enum import Enum

        # Create template with conditional
        test_prompts = {
            "conditional": """% if show_extra:
Extra content
% endif
Main content"""
        }
        (temp_prompts_dir / "test.yaml").write_text(yaml.dump(test_prompts))

        manager = PromptManager(prompts_dir=temp_prompts_dir)

        class TestPrompts(str, Enum):
            CONDITIONAL = "conditional"

        # With extra
        result1 = manager.render("test", TestPrompts.CONDITIONAL, show_extra=True)  # type: ignore
        assert "Extra content" in result1
        assert "Main content" in result1

        # Without extra
        result2 = manager.render("test", TestPrompts.CONDITIONAL, show_extra=False)  # type: ignore
        assert "Extra content" not in result2
        assert "Main content" in result2
