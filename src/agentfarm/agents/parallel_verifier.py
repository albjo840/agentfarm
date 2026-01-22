"""Parallel verification agent for concurrent checks."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from agentfarm.agents.base import AgentContext
from agentfarm.models.schemas import VerificationResult, SingleTestResult
from agentfarm.tools.code_tools import CodeTools

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """Result from a single verification check."""

    check_type: str  # syntax, imports, tests, lint, typecheck
    success: bool
    output: str
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParallelVerificationResult:
    """Result from parallel verification."""

    success: bool
    checks: list[CheckResult]
    total_duration_ms: float
    parallel_speedup: float  # Estimated speedup from parallelization

    @property
    def failed_checks(self) -> list[CheckResult]:
        """Get list of failed checks."""
        return [c for c in self.checks if not c.success]

    def to_verification_result(self) -> VerificationResult:
        """Convert to standard VerificationResult."""
        # Extract data from checks
        tests_passed = 0
        tests_failed = 0
        tests_skipped = 0
        lint_issues: list[str] = []
        type_errors: list[str] = []
        coverage_percent: float | None = None

        for check in self.checks:
            if check.check_type == "tests":
                tests_passed = check.details.get("passed", 0)
                tests_failed = check.details.get("failed", 0)
                tests_skipped = check.details.get("skipped", 0)
            elif check.check_type == "lint":
                lint_issues = check.details.get("issues", [])
            elif check.check_type == "typecheck":
                type_errors = check.details.get("errors", [])
            elif check.check_type == "coverage":
                coverage_percent = check.details.get("percent")

        test_results = [
            SingleTestResult(name=f"test_{i}", passed=True)
            for i in range(tests_passed)
        ] + [
            SingleTestResult(name=f"failed_{i}", passed=False)
            for i in range(tests_failed)
        ]

        return VerificationResult(
            success=self.success,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            tests_skipped=tests_skipped,
            test_results=test_results,
            lint_issues=lint_issues,
            type_errors=type_errors,
            coverage_percent=coverage_percent,
            summary=(
                f"Parallel verification: {len(self.checks)} checks, "
                f"{len(self.failed_checks)} failed. "
                f"Tests: {tests_passed} passed, {tests_failed} failed."
            ),
        )


class ParallelVerifier:
    """Runs verification checks in parallel for faster results.

    Instead of running syntax → imports → tests → lint → typecheck sequentially,
    this runs independent checks concurrently:

    Sequential: |--syntax--|--imports--|--tests--|--lint--|--typecheck--|
    Parallel:   |--syntax--| + |--tests--| + |--lint--| + |--typecheck--|
                |--imports--|

    Typical speedup: 2-3x on multi-core systems.

    Example usage:
        verifier = ParallelVerifier(code_tools=CodeTools("."))

        result = await verifier.verify_files(
            files=["main.py", "utils.py"],
            run_tests=True,
            run_lint=True,
            run_typecheck=True,
        )

        if result.success:
            print("All checks passed!")
        else:
            for check in result.failed_checks:
                print(f"Failed: {check.check_type} - {check.output}")
    """

    def __init__(
        self,
        code_tools: CodeTools | None = None,
        working_dir: str = ".",
        on_check_complete: Callable[[CheckResult], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize parallel verifier.

        Args:
            code_tools: CodeTools instance (created if not provided)
            working_dir: Working directory for checks
            on_check_complete: Optional callback when a check completes
        """
        self.code_tools = code_tools or CodeTools(working_dir)
        self.working_dir = working_dir
        self.on_check_complete = on_check_complete

    async def _check_syntax(self, files: list[str]) -> CheckResult:
        """Check syntax of all files."""
        import ast
        import time
        from pathlib import Path

        start = time.time()
        errors = []

        for file_path in files:
            if not file_path.endswith(".py"):
                continue

            try:
                path = Path(file_path)
                if not path.is_absolute():
                    path = Path(self.working_dir) / path

                if not path.exists():
                    errors.append(f"{file_path}: File not found")
                    continue

                source = path.read_text(encoding="utf-8")
                ast.parse(source)
            except SyntaxError as e:
                errors.append(f"{file_path}:{e.lineno}: {e.msg}")
            except Exception as e:
                errors.append(f"{file_path}: {str(e)}")

        duration_ms = (time.time() - start) * 1000

        result = CheckResult(
            check_type="syntax",
            success=len(errors) == 0,
            output="\n".join(errors) if errors else "All files have valid syntax",
            duration_ms=duration_ms,
            details={"errors": errors, "files_checked": len(files)},
        )

        if self.on_check_complete:
            await self.on_check_complete(result)

        return result

    async def _check_imports(self, files: list[str]) -> CheckResult:
        """Check imports in all files."""
        import ast
        import time
        from pathlib import Path

        start = time.time()
        issues = []

        for file_path in files:
            if not file_path.endswith(".py"):
                continue

            try:
                path = Path(file_path)
                if not path.is_absolute():
                    path = Path(self.working_dir) / path

                if not path.exists():
                    continue

                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)

                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.append(node.module)

                for module in imports:
                    try:
                        __import__(module.split(".")[0])
                    except ImportError:
                        issues.append(f"{file_path}: Cannot import {module}")

            except Exception as e:
                issues.append(f"{file_path}: {str(e)}")

        duration_ms = (time.time() - start) * 1000

        result = CheckResult(
            check_type="imports",
            success=len(issues) == 0,
            output="\n".join(issues) if issues else "All imports valid",
            duration_ms=duration_ms,
            details={"issues": issues},
        )

        if self.on_check_complete:
            await self.on_check_complete(result)

        return result

    async def _run_tests(self, test_path: str = ".") -> CheckResult:
        """Run pytest tests."""
        import time

        start = time.time()

        try:
            output = await self.code_tools.run_tests(path=test_path)

            # Parse output for counts
            passed = output.count(" passed")
            failed = output.count(" failed")
            skipped = output.count(" skipped")

            duration_ms = (time.time() - start) * 1000

            result = CheckResult(
                check_type="tests",
                success=failed == 0,
                output=output,
                duration_ms=duration_ms,
                details={
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped,
                },
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            result = CheckResult(
                check_type="tests",
                success=False,
                output=f"Test execution failed: {e}",
                duration_ms=duration_ms,
                details={"error": str(e)},
            )

        if self.on_check_complete:
            await self.on_check_complete(result)

        return result

    async def _run_lint(self, path: str = ".") -> CheckResult:
        """Run linter."""
        import time

        start = time.time()

        try:
            output = await self.code_tools.run_linter(path=path)

            # Parse for issue count
            issues = [
                line for line in output.split("\n")
                if line.strip() and ":" in line and not line.startswith("Lint:")
            ]

            duration_ms = (time.time() - start) * 1000

            result = CheckResult(
                check_type="lint",
                success=len(issues) == 0,
                output=output,
                duration_ms=duration_ms,
                details={"issues": issues, "count": len(issues)},
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            result = CheckResult(
                check_type="lint",
                success=False,
                output=f"Lint failed: {e}",
                duration_ms=duration_ms,
                details={"error": str(e)},
            )

        if self.on_check_complete:
            await self.on_check_complete(result)

        return result

    async def _run_typecheck(self, path: str = ".") -> CheckResult:
        """Run type checker."""
        import time

        start = time.time()

        try:
            output = await self.code_tools.run_typecheck(path=path)

            # Parse for error count
            errors = [
                line for line in output.split("\n")
                if "error" in line.lower() and not line.startswith("Type check:")
            ]

            duration_ms = (time.time() - start) * 1000

            result = CheckResult(
                check_type="typecheck",
                success=len(errors) == 0,
                output=output,
                duration_ms=duration_ms,
                details={"errors": errors, "count": len(errors)},
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            result = CheckResult(
                check_type="typecheck",
                success=False,
                output=f"Type check failed: {e}",
                duration_ms=duration_ms,
                details={"error": str(e)},
            )

        if self.on_check_complete:
            await self.on_check_complete(result)

        return result

    async def verify_files(
        self,
        files: list[str],
        run_tests: bool = True,
        run_lint: bool = True,
        run_typecheck: bool = True,
        test_path: str = ".",
    ) -> ParallelVerificationResult:
        """Run verification checks in parallel.

        Args:
            files: List of files to check (for syntax/imports)
            run_tests: Whether to run pytest
            run_lint: Whether to run linter
            run_typecheck: Whether to run type checker
            test_path: Path for test execution

        Returns:
            ParallelVerificationResult with all check results
        """
        import time

        start = time.time()

        # Build list of tasks to run in parallel
        tasks = []

        # Syntax check (fast, file-based)
        tasks.append(self._check_syntax(files))

        # Import check (fast, file-based)
        tasks.append(self._check_imports(files))

        # These can run in parallel with each other
        if run_tests:
            tasks.append(self._run_tests(test_path))

        if run_lint:
            tasks.append(self._run_lint(test_path))

        if run_typecheck:
            tasks.append(self._run_typecheck(test_path))

        # Run all checks in parallel
        logger.info("Running %d verification checks in parallel", len(tasks))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        checks: list[CheckResult] = []
        for result in results:
            if isinstance(result, Exception):
                checks.append(CheckResult(
                    check_type="unknown",
                    success=False,
                    output=f"Check failed with exception: {result}",
                    details={"error": str(result)},
                ))
            else:
                checks.append(result)

        total_duration_ms = (time.time() - start) * 1000

        # Calculate sequential time for speedup estimate
        sequential_time = sum(c.duration_ms for c in checks)
        speedup = sequential_time / total_duration_ms if total_duration_ms > 0 else 1.0

        # Overall success = all checks passed
        overall_success = all(c.success for c in checks)

        logger.info(
            "Parallel verification complete: %d checks, %d passed, "
            "%.0fms total (%.1fx speedup)",
            len(checks),
            sum(1 for c in checks if c.success),
            total_duration_ms,
            speedup,
        )

        return ParallelVerificationResult(
            success=overall_success,
            checks=checks,
            total_duration_ms=total_duration_ms,
            parallel_speedup=speedup,
        )

    async def verify_context(
        self,
        context: AgentContext,
        changed_files: list[str],
    ) -> VerificationResult:
        """Verify using AgentContext (compatibility with VerifierAgent).

        Args:
            context: Agent context (used for task info)
            changed_files: Files to verify

        Returns:
            Standard VerificationResult
        """
        result = await self.verify_files(
            files=changed_files,
            run_tests=True,
            run_lint=True,
            run_typecheck=True,
        )
        return result.to_verification_result()
