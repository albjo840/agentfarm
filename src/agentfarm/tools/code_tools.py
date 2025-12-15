from __future__ import annotations

"""Code analysis and testing tools for agents."""

import asyncio
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestRunResult:
    """Result from running tests."""

    passed: int
    failed: int
    skipped: int
    output: str
    duration_ms: int


@dataclass
class LintResult:
    """Result from running linter."""

    issues: list[str]
    fixed: int
    output: str


@dataclass
class TypeCheckResult:
    """Result from type checking."""

    errors: list[str]
    output: str


class CodeTools:
    """Code analysis and testing tools.

    Wraps pytest, ruff, and type checkers for agent use.
    """

    def __init__(self, working_dir: str = ".") -> None:
        self.working_dir = Path(working_dir).resolve()

    async def _run_command(
        self, cmd: list[str], timeout: int = 60
    ) -> tuple[int, str, str]:
        """Run a command and return (returncode, stdout, stderr)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            proc.kill()
            return -1, "", "Command timed out"
        except FileNotFoundError as e:
            return -1, "", f"Command not found: {e}"

    async def run_tests(
        self,
        path: str = ".",
        verbose: bool = False,
        pattern: str | None = None,
    ) -> str:
        """Run pytest tests."""
        cmd = ["python", "-m", "pytest"]

        if verbose:
            cmd.append("-v")

        if pattern:
            cmd.extend(["-k", pattern])

        cmd.append(path)

        returncode, stdout, stderr = await self._run_command(cmd, timeout=120)

        # Parse pytest output for counts
        output = stdout + stderr
        passed = output.count(" passed")
        failed = output.count(" failed")
        skipped = output.count(" skipped")

        result = TestRunResult(
            passed=passed,
            failed=failed,
            skipped=skipped,
            output=output,
            duration_ms=0,
        )

        return (
            f"Tests: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped\n\n{output}"
        )

    async def run_linter(
        self,
        path: str = ".",
        fix: bool = False,
    ) -> str:
        """Run ruff linter."""
        cmd = ["python", "-m", "ruff", "check"]

        if fix:
            cmd.append("--fix")

        cmd.append(path)

        returncode, stdout, stderr = await self._run_command(cmd)
        output = stdout + stderr

        # Parse for issue count
        issues = [line for line in output.split("\n") if line.strip() and ":" in line]

        return f"Lint: {len(issues)} issues found\n\n{output}"

    async def run_formatter(self, path: str = ".") -> str:
        """Run ruff formatter."""
        cmd = ["python", "-m", "ruff", "format", path]
        returncode, stdout, stderr = await self._run_command(cmd)
        return stdout + stderr

    async def run_typecheck(self, path: str = ".") -> str:
        """Run type checker (tries pyright, falls back to mypy)."""
        # Try pyright first
        cmd = ["python", "-m", "pyright", path]
        returncode, stdout, stderr = await self._run_command(cmd)

        if returncode == -1 and "not found" in stderr.lower():
            # Fall back to mypy
            cmd = ["python", "-m", "mypy", path]
            returncode, stdout, stderr = await self._run_command(cmd)

        output = stdout + stderr
        errors = [line for line in output.split("\n") if "error" in line.lower()]

        return f"Type check: {len(errors)} errors\n\n{output}"

    async def get_coverage(self, path: str = ".") -> str:
        """Get test coverage report."""
        cmd = [
            "python", "-m", "pytest",
            "--cov=" + path,
            "--cov-report=term-missing",
            path,
        ]
        returncode, stdout, stderr = await self._run_command(cmd, timeout=120)
        return stdout + stderr

    async def analyze_complexity(self, path: str) -> str:
        """Analyze code complexity (if radon is available)."""
        cmd = ["python", "-m", "radon", "cc", "-a", path]
        returncode, stdout, stderr = await self._run_command(cmd)

        if returncode == -1:
            return "Complexity analysis not available (radon not installed)"

        return stdout + stderr
