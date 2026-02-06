"""QA Runner Service for dynamic validation.

Executes various validation commands:
- Lint (ruff, eslint, etc.)
- Type check (mypy, tsc, etc.)
- Test (pytest, jest, etc.)
- Build verification
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import structlog

from agent.llm.schemas import (
    BuildResult,
    LintResult,
    QAConfig,
    QAValidationType,
    TestResult,
    TypecheckResult,
)

logger = structlog.get_logger()


@dataclass
class CommandResult:
    """Result of running a command."""

    success: bool
    stdout: str
    stderr: str
    return_code: int


class QARunner:
    """Service for running dynamic QA validations.

    Executes lint, type check, test, and build commands based on
    QAConfig settings. Supports Python, JavaScript, and TypeScript
    project types with configurable or default commands.

    Example:
        >>> config = QAConfig(validations=["lint", "typecheck"])
        >>> runner = QARunner(config, project_type="python")
        >>> results = await runner.run_all_validations()
        >>> print(results["lint"].success)
        True
    """

    # Default commands by project type
    DEFAULT_COMMANDS: dict[str, dict[str, str]] = {
        "python": {
            "lint": "ruff check .",
            "typecheck": "mypy src/",
            "test": "pytest --tb=short -q",
            "build": "python -m py_compile",
        },
        "javascript": {
            "lint": "eslint .",
            "typecheck": "tsc --noEmit",
            "test": "npm test",
            "build": "npm run build",
        },
        "typescript": {
            "lint": "eslint .",
            "typecheck": "tsc --noEmit",
            "test": "npm test",
            "build": "npm run build",
        },
    }

    def __init__(self, config: QAConfig, project_type: str = "python") -> None:
        """Initialize QA Runner.

        Args:
            config: QA configuration with validation types and commands
            project_type: Type of project (python, javascript, typescript)
        """
        self.config = config
        self.project_type = project_type
        self.default_commands = self.DEFAULT_COMMANDS.get(project_type, {})

    async def run_all_validations(
        self,
    ) -> dict[str, LintResult | TypecheckResult | TestResult | BuildResult | None]:
        """Run all configured validations.

        Executes each validation type specified in the config sequentially.
        STATIC validation is skipped here as it's handled by QA Agent's LLM analysis.

        Returns:
            Dictionary of validation results keyed by type name.
            Each value is the corresponding result type or None if not configured.
        """
        results: dict[str, LintResult | TypecheckResult | TestResult | BuildResult | None] = {}

        for validation_type in self.config.validations:
            # Compare against string values (QAConfig uses string literals)
            if validation_type == QAValidationType.LINT.value:
                results["lint"] = await self.run_lint()
            elif validation_type == QAValidationType.TYPECHECK.value:
                results["typecheck"] = await self.run_typecheck()
            elif validation_type == QAValidationType.TEST.value:
                results["test"] = await self.run_test()
            elif validation_type == QAValidationType.BUILD.value:
                results["build"] = await self.run_build()
            # STATIC is handled by QA Agent's LLM analysis, not here

        return results

    async def run_lint(self) -> LintResult:
        """Run lint validation.

        Executes the configured lint command (or default for project type).
        Parses output to extract error/warning counts and specific issues.

        Returns:
            LintResult with success status, counts, issues, and raw output.
        """
        command = self.config.lint_command or self.default_commands.get("lint", "")
        if not command:
            return LintResult(
                success=True,
                errors=0,
                warnings=0,
                issues=[],
                output="No lint command configured",
            )

        logger.info("qa_runner_lint_start", command=command)

        result = await self._run_command(command)

        # Parse lint output
        errors, warnings, issues = self._parse_lint_output(result.stdout + result.stderr)

        # Determine success
        success = result.return_code == 0
        if self.config.allow_lint_warnings and errors == 0:
            success = True

        logger.info(
            "qa_runner_lint_complete",
            success=success,
            errors=errors,
            warnings=warnings,
        )

        return LintResult(
            success=success,
            errors=errors,
            warnings=warnings,
            issues=issues,
            output=result.stdout + result.stderr,
        )

    async def run_typecheck(self) -> TypecheckResult:
        """Run type check validation.

        Executes the configured type check command (or default for project type).
        Parses output to extract error counts and specific type issues.

        Returns:
            TypecheckResult with success status, error count, issues, and raw output.
        """
        command = self.config.typecheck_command or self.default_commands.get("typecheck", "")
        if not command:
            return TypecheckResult(
                success=True,
                errors=0,
                issues=[],
                output="No typecheck command configured",
            )

        logger.info("qa_runner_typecheck_start", command=command)

        result = await self._run_command(command)

        # Parse typecheck output
        errors, issues = self._parse_typecheck_output(result.stdout + result.stderr)

        success = result.return_code == 0

        logger.info(
            "qa_runner_typecheck_complete",
            success=success,
            errors=errors,
        )

        return TypecheckResult(
            success=success,
            errors=errors,
            issues=issues,
            output=result.stdout + result.stderr,
        )

    async def run_test(self) -> TestResult:
        """Run test validation.

        Executes the configured test command (or default for project type).
        Uses a 5-minute timeout as tests may take longer.
        Parses output to extract pass/fail/skip counts and failed test names.

        Returns:
            TestResult with success status, counts, coverage, failed tests, and output.
        """
        command = self.config.test_command or self.default_commands.get("test", "")
        if not command:
            return TestResult(
                success=True,
                passed=0,
                failed=0,
                skipped=0,
                total=0,
                coverage=None,
                failed_tests=[],
                output="No test command configured",
            )

        logger.info("qa_runner_test_start", command=command)

        result = await self._run_command(command, timeout=300)  # 5 min timeout for tests

        # Parse test output
        passed, failed, skipped, failed_tests, coverage = self._parse_test_output(
            result.stdout + result.stderr
        )

        success = result.return_code == 0
        if self.config.require_all_tests_pass and failed > 0:
            success = False

        logger.info(
            "qa_runner_test_complete",
            success=success,
            passed=passed,
            failed=failed,
            skipped=skipped,
        )

        return TestResult(
            success=success,
            passed=passed,
            failed=failed,
            skipped=skipped,
            total=passed + failed + skipped,
            coverage=coverage,
            failed_tests=failed_tests,
            output=result.stdout + result.stderr,
        )

    async def run_build(self) -> BuildResult:
        """Run build validation.

        Executes the configured build command (or default for project type).
        Uses a 10-minute timeout as builds may be lengthy.

        Returns:
            BuildResult with success status, output, and error message if failed.
        """
        command = self.config.build_command or self.default_commands.get("build", "")
        if not command:
            return BuildResult(
                success=True,
                output="No build command configured",
                error_message=None,
            )

        logger.info("qa_runner_build_start", command=command)

        result = await self._run_command(command, timeout=600)  # 10 min timeout for build

        success = result.return_code == 0
        error_message = result.stderr if not success else None

        logger.info("qa_runner_build_complete", success=success)

        return BuildResult(
            success=success,
            output=result.stdout,
            error_message=error_message,
        )

    async def _run_command(self, command: str, timeout: int = 120) -> CommandResult:
        """Run a shell command asynchronously.

        Args:
            command: Shell command to execute
            timeout: Timeout in seconds (default 120)

        Returns:
            CommandResult with stdout, stderr, success status, and return code.
        """
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            return CommandResult(
                success=process.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                return_code=process.returncode or 0,
            )
        except TimeoutError:
            logger.warning("qa_runner_command_timeout", command=command, timeout=timeout)
            return CommandResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                return_code=-1,
            )
        except Exception as e:
            logger.error("qa_runner_command_error", command=command, error=str(e))
            return CommandResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
            )

    def _parse_lint_output(self, output: str) -> tuple[int, int, list[str]]:
        """Parse lint command output.

        Supports ruff and eslint output formats. Extracts error/warning counts
        and individual issues.

        Args:
            output: Combined stdout and stderr from lint command

        Returns:
            Tuple of (error_count, warning_count, issue_list).
            Issue list is limited to first 20 issues.
        """
        errors = 0
        warnings = 0
        issues: list[str] = []

        lines = output.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Ruff format: file:line:col: ERROR message
            # ESLint format: file:line:col: error/warning message
            if ": error" in line.lower() or line.startswith("E"):
                errors += 1
                issues.append(line)
            elif ": warning" in line.lower() or line.startswith("W"):
                warnings += 1
                issues.append(line)
            elif re.match(r".*:\d+:\d+:", line):
                issues.append(line)
                if "error" in line.lower():
                    errors += 1
                else:
                    warnings += 1

        return errors, warnings, issues[:20]  # Limit to 20 issues

    def _parse_typecheck_output(self, output: str) -> tuple[int, list[str]]:
        """Parse typecheck command output.

        Supports mypy and tsc output formats.

        Args:
            output: Combined stdout and stderr from typecheck command

        Returns:
            Tuple of (error_count, issue_list).
            Issue list is limited to first 20 issues.
        """
        errors = 0
        issues: list[str] = []

        lines = output.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # mypy format: file:line: error: message
            # tsc format: file(line,col): error TSxxxx: message
            if ": error:" in line.lower() or "error TS" in line:
                errors += 1
                issues.append(line)

        return errors, issues[:20]

    def _parse_test_output(self, output: str) -> tuple[int, int, int, list[str], float | None]:
        """Parse test command output.

        Supports pytest output format. Extracts pass/fail/skip counts,
        coverage percentage, and names of failed tests.

        Args:
            output: Combined stdout and stderr from test command

        Returns:
            Tuple of (passed, failed, skipped, failed_test_names, coverage_percent).
            Coverage is None if not found in output.
        """
        passed = 0
        failed = 0
        skipped = 0
        failed_tests: list[str] = []
        coverage: float | None = None

        # Pytest format: X passed, Y failed, Z skipped
        match = re.search(r"(\d+) passed", output)
        if match:
            passed = int(match.group(1))

        match = re.search(r"(\d+) failed", output)
        if match:
            failed = int(match.group(1))

        match = re.search(r"(\d+) skipped", output)
        if match:
            skipped = int(match.group(1))

        # Coverage percentage (e.g., "TOTAL 1234 456 63%")
        match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if match:
            coverage = float(match.group(1))
        else:
            # Alternative format: just percentage
            match = re.search(r"(\d+)%\s*$", output, re.MULTILINE)
            if match:
                coverage = float(match.group(1))

        # Failed test names
        for line in output.split("\n"):
            if "FAILED" in line:
                # Extract test name (format: FAILED path/to/test.py::test_name)
                match = re.search(r"FAILED\s+(\S+)", line)
                if match:
                    failed_tests.append(match.group(1))

        return passed, failed, skipped, failed_tests, coverage
