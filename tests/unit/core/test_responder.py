"""Tests for ResponderAgent."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from bsai.core.responder import (
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

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
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

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
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

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
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

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
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

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            await responder.generate_response(
                task_id=task_id,
                original_request="Test request",
                worker_output="Test output",
            )

        mock_router.select_model.assert_called_once()
        # Verify TaskComplexity.SIMPLE was used
        call_args = mock_router.select_model.call_args
        from bsai.db.models.enums import TaskComplexity

        assert call_args[0][0] == TaskComplexity.SIMPLE

    async def test_generate_failure_report_success(
        self,
        responder: ResponderAgent,
        mock_llm_client,
        mock_router,
        mock_prompt_manager,
    ):
        """Test generating failure report successfully."""
        task_id = uuid4()

        mock_response = MagicMock()
        mock_response.content = "Failure report content"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 200
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_response)

        failure_context = {
            "attempted_milestones": [
                {"description": "Step 1", "status": "passed"},
                {"description": "Step 2", "status": "failed", "qa_feedback": "Error occurred"},
            ],
            "final_error": "Task failed after max retries",
        }

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            result = await responder.generate_failure_report(
                task_id=task_id,
                original_request="Build a web app",
                failure_context=failure_context,
            )

        assert result == "Failure report content"
        mock_llm_client.chat_completion.assert_called_once()

    async def test_generate_failure_report_korean_request(
        self,
        responder: ResponderAgent,
        mock_llm_client,
        mock_prompt_manager,
    ):
        """Test generating failure report for Korean request."""
        task_id = uuid4()

        mock_response = MagicMock()
        mock_response.content = "실패 보고서"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 150
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_response)

        failure_context = {
            "attempted_milestones": [],
            "final_error": "Unknown error",
        }

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            result = await responder.generate_failure_report(
                task_id=task_id,
                original_request="한국어 요청입니다",
                failure_context=failure_context,
            )

        assert result == "실패 보고서"
        render_calls = mock_prompt_manager.render.call_args_list
        assert any("Korean" in str(call) for call in render_calls)

    async def test_generate_failure_report_with_partial_results(
        self,
        responder: ResponderAgent,
        mock_llm_client,
    ):
        """Test failure report includes partial results from passed milestones."""
        task_id = uuid4()

        mock_response = MagicMock()
        mock_response.content = "Report with partial results"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 180
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_response)

        failure_context = {
            "attempted_milestones": [
                {
                    "description": "Create file",
                    "status": "passed",
                    "worker_output": "File created successfully with content xyz",
                },
                {
                    "description": "Deploy app",
                    "status": "failed",
                    "qa_feedback": "Deployment failed",
                },
            ],
            "final_error": "Deployment error",
        }

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            result = await responder.generate_failure_report(
                task_id=task_id,
                original_request="Deploy my app",
                failure_context=failure_context,
            )

        assert result == "Report with partial results"

    async def test_generate_failure_report_empty_milestones(
        self,
        responder: ResponderAgent,
        mock_llm_client,
    ):
        """Test failure report with no milestones attempted."""
        task_id = uuid4()

        mock_response = MagicMock()
        mock_response.content = "No progress report"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 100
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_response)

        failure_context = {
            "attempted_milestones": [],
            "final_error": None,
        }

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            result = await responder.generate_failure_report(
                task_id=task_id,
                original_request="Do something",
                failure_context=failure_context,
            )

        assert result == "No progress report"

    async def test_generate_failure_report_uses_moderate_model(
        self,
        responder: ResponderAgent,
        mock_router,
        mock_llm_client,
    ):
        """Test that MODERATE complexity model is used for failure reports."""
        task_id = uuid4()

        mock_response = MagicMock()
        mock_response.content = "Report"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 100
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_response)

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            await responder.generate_failure_report(
                task_id=task_id,
                original_request="Test",
                failure_context={"attempted_milestones": [], "final_error": "Error"},
            )

        from bsai.db.models.enums import TaskComplexity

        call_args = mock_router.select_model.call_args
        assert call_args[0][0] == TaskComplexity.MODERATE

    async def test_generate_failure_report_with_status_enum(
        self,
        responder: ResponderAgent,
        mock_llm_client,
    ):
        """Test failure report handles status as enum object."""
        task_id = uuid4()

        class MockStatus:
            value = "passed"

        mock_response = MagicMock()
        mock_response.content = "Report"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 100
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_response)

        failure_context = {
            "attempted_milestones": [
                {"description": "Step 1", "status": MockStatus()},
            ],
            "final_error": "Error",
        }

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            result = await responder.generate_failure_report(
                task_id=task_id,
                original_request="Test",
                failure_context=failure_context,
            )

        assert result == "Report"

    async def test_generate_failure_report_with_pass_status(
        self,
        responder: ResponderAgent,
        mock_llm_client,
    ):
        """Test failure report handles 'pass' status string."""
        task_id = uuid4()

        mock_response = MagicMock()
        mock_response.content = "Report with pass status"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 100
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_response)

        failure_context = {
            "attempted_milestones": [
                {
                    "description": "Step 1",
                    "status": "pass",
                    "worker_output": "Step completed",
                },
            ],
            "final_error": "Error",
        }

        with patch("bsai.core.responder.get_agent_settings") as mock_settings:
            mock_settings.return_value.worker_temperature = 0.7

            result = await responder.generate_failure_report(
                task_id=task_id,
                original_request="Test",
                failure_context=failure_context,
            )

        assert result == "Report with pass status"
