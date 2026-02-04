"""QA Agent for output validation and feedback.

The QA Agent is responsible for:
1. Validating Worker outputs against acceptance criteria
2. Providing structured feedback for improvements
3. Deciding whether to pass, fail, or retry
4. Tracking validation history
5. Running dynamic validations (lint, typecheck, test, build)
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.api.websocket.manager import ConnectionManager
from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.db.models.mcp_server_config import McpServerConfig
from agent.db.repository.mcp_server_repo import McpServerRepository
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMRouter
from agent.llm.schemas import (
    BuildResult,
    LintResult,
    QAConfig,
    QAOutput,
    QAValidationType,
    TestResult,
    TypecheckResult,
)
from agent.mcp.executor import McpToolExecutor
from agent.mcp.utils import load_user_mcp_servers
from agent.prompts import PromptManager, QAAgentPrompts
from agent.services.qa_runner import QARunner

logger = structlog.get_logger()


class QADecision(str, Enum):
    """QA validation decision.

    Note: FAIL is only set by the system when max retries are exceeded.
    The QA prompt only offers PASS/RETRY options to prevent premature failure.
    """

    PASS = "pass"
    RETRY = "retry"
    FAIL = "fail"  # Only set by system when max retries exceeded


class AggregatedQAResult:
    """Container for aggregated QA validation results.

    Holds both static (LLM) analysis and dynamic validation results.
    """

    def __init__(
        self,
        static_result: QAOutput,
        lint_result: LintResult | None = None,
        typecheck_result: TypecheckResult | None = None,
        test_result: TestResult | None = None,
        build_result: BuildResult | None = None,
    ) -> None:
        """Initialize aggregated result.

        Args:
            static_result: LLM-based static analysis result
            lint_result: Lint validation result
            typecheck_result: Type check validation result
            test_result: Test execution result
            build_result: Build verification result
        """
        self.static_result = static_result
        self.lint_result = lint_result
        self.typecheck_result = typecheck_result
        self.test_result = test_result
        self.build_result = build_result

    @property
    def all_passed(self) -> bool:
        """Check if all validations passed.

        Returns:
            True if all configured validations passed.
        """
        static_passed = self.static_result.decision == "PASS"
        lint_passed = self.lint_result is None or self.lint_result.success
        typecheck_passed = self.typecheck_result is None or self.typecheck_result.success
        test_passed = self.test_result is None or self.test_result.success
        build_passed = self.build_result is None or self.build_result.success

        return all([static_passed, lint_passed, typecheck_passed, test_passed, build_passed])


class QAAgent:
    """QA agent for validating Worker outputs.

    Uses a medium-complexity LLM to provide independent validation
    and structured feedback for quality assurance. Supports dynamic
    validations including lint, typecheck, test, and build.
    """

    def __init__(
        self,
        llm_client: LiteLLMClient,
        router: LLMRouter,
        prompt_manager: PromptManager,
        session: AsyncSession,
        ws_manager: ConnectionManager | None = None,
        qa_config: QAConfig | None = None,
        project_type: str = "python",
    ) -> None:
        """Initialize QA agent.

        Args:
            llm_client: LLM client for API calls
            router: Router for model selection
            prompt_manager: Prompt manager for template rendering
            session: Database session
            ws_manager: Optional WebSocket manager for MCP stdio tools
            qa_config: QA configuration for dynamic validations
            project_type: Project type for default commands (python, javascript, typescript)
        """
        self.llm_client = llm_client
        self.router = router
        self.prompt_manager = prompt_manager
        self.session = session
        self.milestone_repo = MilestoneRepository(session)
        self.mcp_server_repo = McpServerRepository(session)
        self.ws_manager = ws_manager
        self.qa_config = qa_config or QAConfig()
        self.project_type = project_type

    async def validate_output(
        self,
        milestone_id: UUID,
        milestone_description: str,
        acceptance_criteria: str,
        worker_output: str,
        user_id: str,
        session_id: UUID,
        mcp_enabled: bool = True,
    ) -> tuple[QADecision, str, QAOutput]:
        """Validate Worker output against acceptance criteria.

        Runs both static (LLM-based) analysis and dynamic validations
        (lint, typecheck, test, build) based on qa_config settings.

        Args:
            milestone_id: Milestone ID being validated
            milestone_description: Original milestone description
            acceptance_criteria: Success criteria
            worker_output: Output from Worker agent
            user_id: User ID for MCP tool ownership
            session_id: Session ID for MCP tool logging
            mcp_enabled: Enable MCP tool calling (default: True)

        Returns:
            Tuple of (decision, feedback, qa_output):
                - decision: PASS or RETRY
                - feedback: Structured feedback for Worker (includes dynamic results)
                - qa_output: Full QAOutput including plan viability assessment

        Raises:
            ValueError: If LLM response is invalid
        """
        logger.info(
            "qa_validation_start",
            milestone_id=str(milestone_id),
            output_length=len(worker_output),
            mcp_enabled=mcp_enabled,
            validations=self.qa_config.validations,
        )

        # Step 1: Run static analysis (LLM-based)
        static_result = await self._run_static_analysis(
            milestone_id=milestone_id,
            milestone_description=milestone_description,
            acceptance_criteria=acceptance_criteria,
            worker_output=worker_output,
            user_id=user_id,
            session_id=session_id,
            mcp_enabled=mcp_enabled,
        )

        # Step 2: Run dynamic validations (lint, typecheck, test, build)
        dynamic_results = await self._run_dynamic_validations()

        # Step 3: Aggregate all results
        aggregated = self._aggregate_results(static_result, dynamic_results)

        # Determine final decision based on aggregated results
        if aggregated.all_passed:
            final_decision = QADecision.PASS
        else:
            final_decision = QADecision.RETRY

        # Step 4: Generate human-readable summary
        summary = self._generate_summary(aggregated)

        # Build combined feedback
        feedback_parts = [static_result.feedback]

        if final_decision == QADecision.RETRY and static_result.issues:
            feedback_parts.append("\n\nISSUES FOUND (STATIC ANALYSIS):")
            for issue in static_result.issues:
                feedback_parts.append(f"- {issue}")

        if final_decision == QADecision.RETRY and static_result.suggestions:
            feedback_parts.append("\n\nSUGGESTIONS:")
            for suggestion in static_result.suggestions:
                feedback_parts.append(f"- {suggestion}")

        # Add dynamic validation summary
        feedback_parts.append(f"\n\n{summary}")

        formatted_feedback = "\n".join(feedback_parts)

        # Update milestone status based on final decision
        await self._update_milestone_status(milestone_id, final_decision)

        logger.info(
            "qa_validation_complete",
            milestone_id=str(milestone_id),
            decision=final_decision.value,
            static_decision=static_result.decision,
            plan_viability=static_result.plan_viability,
            confidence=static_result.confidence,
            lint_passed=aggregated.lint_result.success if aggregated.lint_result else None,
            typecheck_passed=(
                aggregated.typecheck_result.success if aggregated.typecheck_result else None
            ),
            test_passed=aggregated.test_result.success if aggregated.test_result else None,
            build_passed=aggregated.build_result.success if aggregated.build_result else None,
        )

        return final_decision, formatted_feedback, static_result

    async def _run_static_analysis(
        self,
        milestone_id: UUID,
        milestone_description: str,
        acceptance_criteria: str,
        worker_output: str,
        user_id: str,
        session_id: UUID,
        mcp_enabled: bool = True,
    ) -> QAOutput:
        """Run static (LLM-based) analysis on worker output.

        Args:
            milestone_id: Milestone ID being validated
            milestone_description: Original milestone description
            acceptance_criteria: Success criteria
            worker_output: Output from Worker agent
            user_id: User ID for MCP tool ownership
            session_id: Session ID for MCP tool logging
            mcp_enabled: Enable MCP tool calling

        Returns:
            QAOutput from LLM analysis

        Raises:
            ValueError: If LLM response is invalid
        """
        logger.debug(
            "qa_static_analysis_start",
            milestone_id=str(milestone_id),
        )

        # Use MODERATE complexity for QA (medium LLM)
        model = self.router.select_model(TaskComplexity.MODERATE)

        # Build validation prompt
        validation_prompt = self._build_validation_prompt(
            milestone_description,
            acceptance_criteria,
            worker_output,
        )

        messages = [ChatMessage(role="user", content=validation_prompt)]

        # Call LLM with structured output
        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=settings.qa_temperature,
            api_base=model.api_base,
            api_key=model.api_key,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "qa_output",
                    "strict": True,
                    "schema": QAOutput.model_json_schema(),
                },
            },
        )

        # Load MCP servers if enabled
        mcp_servers: list[McpServerConfig] = []
        tool_executor: McpToolExecutor | None = None

        if mcp_enabled:
            mcp_servers = await load_user_mcp_servers(
                mcp_server_repo=self.mcp_server_repo,
                user_id=user_id,
                agent_type="qa",
            )

            if mcp_servers:
                tool_executor = McpToolExecutor(
                    user_id=user_id,
                    session_id=session_id,
                    ws_manager=self.ws_manager,
                )
                # Register executor in ConnectionManager for WebSocket access
                if self.ws_manager:
                    self.ws_manager.register_mcp_executor(session_id, tool_executor)
                logger.info(
                    "qa_mcp_enabled",
                    milestone_id=str(milestone_id),
                    mcp_server_count=len(mcp_servers),
                )

        # Execute with or without tools (unified interface)
        response = await self.llm_client.chat_completion(
            request=request,
            mcp_servers=mcp_servers if tool_executor else [],
            tool_executor=tool_executor,
        )

        # Parse structured response
        try:
            output = QAOutput.model_validate_json(response.content)
        except (ValueError, KeyError) as e:
            logger.error(
                "qa_static_parse_failed",
                milestone_id=str(milestone_id),
                error=str(e),
                response=response.content[:500],
            )
            raise ValueError(f"Failed to parse QA response: {e}") from e

        logger.debug(
            "qa_static_analysis_complete",
            milestone_id=str(milestone_id),
            decision=output.decision,
            tokens=response.usage.total_tokens,
        )

        return output

    async def _run_dynamic_validations(
        self,
    ) -> dict[str, LintResult | TypecheckResult | TestResult | BuildResult | None]:
        """Run dynamic validations based on qa_config.

        Executes lint, typecheck, test, and build validations as configured.

        Returns:
            Dictionary of validation results keyed by type name.
        """
        # Check if any dynamic validations are configured
        dynamic_types = {
            QAValidationType.LINT.value,
            QAValidationType.TYPECHECK.value,
            QAValidationType.TEST.value,
            QAValidationType.BUILD.value,
        }

        configured_dynamic = [v for v in self.qa_config.validations if v in dynamic_types]

        if not configured_dynamic:
            logger.debug("qa_no_dynamic_validations_configured")
            return {}

        logger.info(
            "qa_dynamic_validations_start",
            validations=configured_dynamic,
            project_type=self.project_type,
        )

        # Create QARunner and execute validations
        runner = QARunner(config=self.qa_config, project_type=self.project_type)
        results = await runner.run_all_validations()

        # Extract results with proper type checking
        lint_res = results.get("lint")
        typecheck_res = results.get("typecheck")
        test_res = results.get("test")
        build_res = results.get("build")

        logger.info(
            "qa_dynamic_validations_complete",
            lint_success=lint_res.success if lint_res is not None else None,
            typecheck_success=typecheck_res.success if typecheck_res is not None else None,
            test_success=test_res.success if test_res is not None else None,
            build_success=build_res.success if build_res is not None else None,
        )

        return results

    def _aggregate_results(
        self,
        static_result: QAOutput,
        dynamic_results: dict[str, LintResult | TypecheckResult | TestResult | BuildResult | None],
    ) -> AggregatedQAResult:
        """Aggregate all validation results into a single container.

        Args:
            static_result: LLM-based static analysis result
            dynamic_results: Dictionary of dynamic validation results

        Returns:
            AggregatedQAResult containing all results
        """
        lint_result = dynamic_results.get("lint")
        typecheck_result = dynamic_results.get("typecheck")
        test_result = dynamic_results.get("test")
        build_result = dynamic_results.get("build")

        # Ensure correct types (narrow from union type)
        aggregated = AggregatedQAResult(
            static_result=static_result,
            lint_result=lint_result if isinstance(lint_result, LintResult) else None,
            typecheck_result=(
                typecheck_result if isinstance(typecheck_result, TypecheckResult) else None
            ),
            test_result=test_result if isinstance(test_result, TestResult) else None,
            build_result=build_result if isinstance(build_result, BuildResult) else None,
        )

        logger.debug(
            "qa_results_aggregated",
            static_passed=static_result.decision == "PASS",
            lint_passed=aggregated.lint_result.success if aggregated.lint_result else "N/A",
            typecheck_passed=(
                aggregated.typecheck_result.success if aggregated.typecheck_result else "N/A"
            ),
            test_passed=aggregated.test_result.success if aggregated.test_result else "N/A",
            build_passed=aggregated.build_result.success if aggregated.build_result else "N/A",
            all_passed=aggregated.all_passed,
        )

        return aggregated

    def _generate_summary(self, aggregated: AggregatedQAResult) -> str:
        """Generate human-readable summary of all validation results.

        Args:
            aggregated: Aggregated validation results

        Returns:
            Formatted summary string
        """
        summary_parts: list[str] = ["DYNAMIC VALIDATION SUMMARY:"]

        # Static analysis summary
        static_status = "PASS" if aggregated.static_result.decision == "PASS" else "RETRY"
        summary_parts.append(f"- Static Analysis: {static_status}")

        # Lint result
        if aggregated.lint_result is not None:
            lint_status = "PASS" if aggregated.lint_result.success else "FAIL"
            lint_detail = f" ({aggregated.lint_result.errors} errors, {aggregated.lint_result.warnings} warnings)"
            summary_parts.append(f"- Lint: {lint_status}{lint_detail}")

            # Show first few lint issues if failed
            if not aggregated.lint_result.success and aggregated.lint_result.issues:
                for issue in aggregated.lint_result.issues[:3]:
                    summary_parts.append(f"    - {issue}")
                if len(aggregated.lint_result.issues) > 3:
                    remaining = len(aggregated.lint_result.issues) - 3
                    summary_parts.append(f"    ... and {remaining} more issues")

        # Typecheck result
        if aggregated.typecheck_result is not None:
            tc_status = "PASS" if aggregated.typecheck_result.success else "FAIL"
            tc_detail = f" ({aggregated.typecheck_result.errors} errors)"
            summary_parts.append(f"- Type Check: {tc_status}{tc_detail}")

            # Show first few type errors if failed
            if not aggregated.typecheck_result.success and aggregated.typecheck_result.issues:
                for issue in aggregated.typecheck_result.issues[:3]:
                    summary_parts.append(f"    - {issue}")
                if len(aggregated.typecheck_result.issues) > 3:
                    remaining = len(aggregated.typecheck_result.issues) - 3
                    summary_parts.append(f"    ... and {remaining} more issues")

        # Test result
        if aggregated.test_result is not None:
            test_status = "PASS" if aggregated.test_result.success else "FAIL"
            test_detail = (
                f" ({aggregated.test_result.passed} passed, "
                f"{aggregated.test_result.failed} failed, "
                f"{aggregated.test_result.skipped} skipped)"
            )
            summary_parts.append(f"- Tests: {test_status}{test_detail}")

            # Show coverage if available
            if aggregated.test_result.coverage is not None:
                summary_parts.append(f"    Coverage: {aggregated.test_result.coverage:.1f}%")

            # Show failed tests if any
            if not aggregated.test_result.success and aggregated.test_result.failed_tests:
                summary_parts.append("    Failed tests:")
                for test_name in aggregated.test_result.failed_tests[:5]:
                    summary_parts.append(f"      - {test_name}")
                if len(aggregated.test_result.failed_tests) > 5:
                    remaining = len(aggregated.test_result.failed_tests) - 5
                    summary_parts.append(f"      ... and {remaining} more")

        # Build result
        if aggregated.build_result is not None:
            build_status = "PASS" if aggregated.build_result.success else "FAIL"
            summary_parts.append(f"- Build: {build_status}")

            if not aggregated.build_result.success and aggregated.build_result.error_message:
                error_preview = aggregated.build_result.error_message[:200]
                if len(aggregated.build_result.error_message) > 200:
                    error_preview += "..."
                summary_parts.append(f"    Error: {error_preview}")

        # Overall result
        overall = "PASS" if aggregated.all_passed else "RETRY"
        summary_parts.append(f"\nOVERALL: {overall}")

        return "\n".join(summary_parts)

    def _build_validation_prompt(
        self,
        milestone_description: str,
        acceptance_criteria: str,
        worker_output: str,
    ) -> str:
        """Build validation prompt for QA.

        Args:
            milestone_description: Original milestone description
            acceptance_criteria: Success criteria
            worker_output: Output to validate

        Returns:
            Formatted validation prompt
        """
        return self.prompt_manager.render(
            "qa_agent",
            QAAgentPrompts.VALIDATION_PROMPT,
            milestone_description=milestone_description,
            acceptance_criteria=acceptance_criteria,
            worker_output=worker_output,
        )

    def _parse_validation_response(
        self,
        response_content: str,
    ) -> tuple[QADecision, str, QAOutput]:
        """Parse QA validation response.

        Args:
            response_content: Raw LLM response (structured JSON)

        Returns:
            Tuple of (decision, formatted_feedback, raw_output):
                - decision: QADecision enum
                - formatted_feedback: Human-readable feedback string
                - raw_output: Full QAOutput for plan viability info

        Raises:
            ValueError: If response validation fails
        """
        # Parse using Pydantic model
        output = QAOutput.model_validate_json(response_content)

        # Map decision string to enum
        if output.decision == "PASS":
            decision = QADecision.PASS
        else:
            decision = QADecision.RETRY

        # Format feedback
        feedback_parts = [output.feedback]

        if decision == QADecision.RETRY and output.issues:
            feedback_parts.append("\n\nISSUES FOUND:")
            for issue in output.issues:
                feedback_parts.append(f"- {issue}")

        if decision == QADecision.RETRY and output.suggestions:
            feedback_parts.append("\n\nSUGGESTIONS:")
            for suggestion in output.suggestions:
                feedback_parts.append(f"- {suggestion}")

        formatted_feedback = "\n".join(feedback_parts)

        return decision, formatted_feedback, output

    async def _update_milestone_status(
        self,
        milestone_id: UUID,
        decision: QADecision,
    ) -> None:
        """Update milestone status based on QA decision.

        Args:
            milestone_id: Milestone ID
            decision: QA decision
        """
        # Map QADecision to MilestoneStatus
        status_mapping = {
            QADecision.PASS: MilestoneStatus.PASSED,
            QADecision.RETRY: MilestoneStatus.IN_PROGRESS,
            QADecision.FAIL: MilestoneStatus.FAILED,
        }
        milestone_status = status_mapping.get(decision, MilestoneStatus.IN_PROGRESS)

        await self.milestone_repo.update(
            milestone_id,
            status=milestone_status.value,
        )

        logger.debug(
            "milestone_status_updated",
            milestone_id=str(milestone_id),
            status=milestone_status.value,
        )
