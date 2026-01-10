"""Tests for ResponderAgent."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.core.responder import (
    ResponderAgent,
    detect_language,
    get_language_name,
)


class TestDetectLanguage:
    """Tests for detect_language function."""

    def test_detect_english(self):
        """Test detecting English text."""
        text = "Hello, how are you today? This is a test message."
        result = detect_language(text)
        assert result == "en"

    def test_detect_korean(self):
        """Test detecting Korean text."""
        text = "안녕하세요, 오늘 어떠세요? 이것은 테스트 메시지입니다."
        result = detect_language(text)
        assert result == "ko"

    def test_detect_japanese(self):
        """Test detecting Japanese text."""
        text = "こんにちは、今日はどうですか？これはテストメッセージです。"
        result = detect_language(text)
        assert result == "ja"

    def test_detect_chinese(self):
        """Test detecting Chinese text."""
        text = "你好，今天怎么样？这是一条测试消息。"
        result = detect_language(text)
        assert result == "zh"

    def test_detect_empty_string(self):
        """Test detecting empty string returns English."""
        result = detect_language("")
        assert result == "en"

    def test_detect_whitespace_only(self):
        """Test detecting whitespace-only string returns English."""
        result = detect_language("   ")
        assert result == "en"

    def test_detect_none_returns_english(self):
        """Test that None-like input returns English."""
        # Empty string case
        result = detect_language("")
        assert result == "en"


class TestGetLanguageName:
    """Tests for get_language_name function."""

    def test_get_english_name(self):
        """Test getting English language name."""
        result = get_language_name("en")
        assert result == "English"

    def test_get_korean_name(self):
        """Test getting Korean language name."""
        result = get_language_name("ko")
        assert result == "Korean"

    def test_get_japanese_name(self):
        """Test getting Japanese language name."""
        result = get_language_name("ja")
        assert result == "Japanese"

    def test_get_chinese_name(self):
        """Test getting Chinese language name."""
        result = get_language_name("zh")
        assert result == "Chinese"

    def test_get_unknown_code_returns_english(self):
        """Test that unknown code returns English."""
        result = get_language_name("xyz")
        assert result == "English"

    def test_get_case_insensitive(self):
        """Test that language code is case insensitive."""
        result_lower = get_language_name("en")
        result_upper = get_language_name("EN")
        assert result_lower == result_upper == "English"


class TestResponderAgent:
    """Tests for ResponderAgent class."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Generated response"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 100
        client.chat_completion = AsyncMock(return_value=mock_response)
        return client

    @pytest.fixture
    def mock_router(self):
        """Create mock LLM router."""
        router = MagicMock()
        mock_model = MagicMock()
        mock_model.name = "gpt-4"
        mock_model.api_base = None
        mock_model.api_key = None
        router.select_model = MagicMock(return_value=mock_model)
        return router

    @pytest.fixture
    def mock_prompt_manager(self):
        """Create mock prompt manager."""
        manager = MagicMock()
        manager.render = MagicMock(return_value="Rendered prompt")
        return manager

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def responder(
        self,
        mock_llm_client,
        mock_router,
        mock_prompt_manager,
        mock_session,
    ):
        """Create ResponderAgent instance."""
        return ResponderAgent(
            llm_client=mock_llm_client,
            router=mock_router,
            prompt_manager=mock_prompt_manager,
            session=mock_session,
        )

    async def test_generate_response_success(
        self,
        responder: ResponderAgent,
        mock_llm_client,
        mock_prompt_manager,
    ):
        """Test generating response successfully."""
        task_id = uuid4()

        with patch("agent.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            result = await responder.generate_response(
                task_id=task_id,
                original_request="Hello, help me with Python",
                worker_output="Here is the Python code: print('hello')",
                has_artifacts=True,
            )

        assert result == "Generated response"
        mock_llm_client.chat_completion.assert_called_once()
        mock_prompt_manager.render.assert_called()

    async def test_generate_response_korean_request(
        self,
        responder: ResponderAgent,
        mock_llm_client,
        mock_prompt_manager,
    ):
        """Test generating response for Korean request."""
        task_id = uuid4()

        with patch("agent.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            result = await responder.generate_response(
                task_id=task_id,
                original_request="안녕하세요, Python 도움이 필요합니다",
                worker_output="Here is the code",
                has_artifacts=False,
            )

        assert result == "Generated response"
        # Check that Korean language was detected and passed to prompt
        render_calls = mock_prompt_manager.render.call_args_list
        # At least one call should include Korean language
        assert any("Korean" in str(call) for call in render_calls)

    async def test_generate_response_no_artifacts(
        self,
        responder: ResponderAgent,
        mock_llm_client,
        mock_prompt_manager,
    ):
        """Test generating response without artifacts."""
        task_id = uuid4()

        with patch("agent.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            result = await responder.generate_response(
                task_id=task_id,
                original_request="What is Python?",
                worker_output="Python is a programming language",
                has_artifacts=False,
            )

        assert result == "Generated response"
        # Verify has_artifacts=False was passed to prompt
        render_calls = mock_prompt_manager.render.call_args_list
        assert any("has_artifacts" in str(call) for call in render_calls)

    async def test_generate_response_strips_whitespace(
        self,
        responder: ResponderAgent,
        mock_llm_client,
    ):
        """Test that response is stripped of whitespace."""
        mock_response = MagicMock()
        mock_response.content = "  Response with whitespace  \n"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_response)

        task_id = uuid4()

        with patch("agent.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            result = await responder.generate_response(
                task_id=task_id,
                original_request="Test",
                worker_output="Output",
            )

        assert result == "Response with whitespace"

    async def test_generate_response_selects_simple_model(
        self,
        responder: ResponderAgent,
        mock_router,
    ):
        """Test that SIMPLE complexity model is selected."""
        task_id = uuid4()

        with patch("agent.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            await responder.generate_response(
                task_id=task_id,
                original_request="Test request",
                worker_output="Test output",
            )

        mock_router.select_model.assert_called_once()
        # Verify TaskComplexity.SIMPLE was used
        call_args = mock_router.select_model.call_args
        from agent.db.models.enums import TaskComplexity

        assert call_args[0][0] == TaskComplexity.SIMPLE
