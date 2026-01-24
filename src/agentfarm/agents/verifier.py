from __future__ import annotations

"""VerifierAgent - runs tests and validates changes."""

import json
from typing import Any

from agentfarm.agents.base import AgentContext, AgentResult, BaseAgent
from agentfarm.models.schemas import SingleTestResult, VerificationResult
from agentfarm.providers.base import CompletionResponse, LLMProvider, ToolDefinition


class VerifierAgent(BaseAgent):
    """Agent responsible for verifying code changes.

    Runs tests, linting, type checking to ensure changes are valid.
    """

    name = "VerifierAgent"
    description = "Verifies code changes through testing and validation"
    default_max_tool_calls = 40  # Verifier needs many tool calls (syntax, imports, tests, lint, typecheck)

    def __init__(self, provider: LLMProvider, working_dir: str = ".") -> None:
        super().__init__(provider)
        from pathlib import Path
        self._working_dir = Path(working_dir).resolve()
        self._failed_paths: set[str] = set()  # Track paths that don't exist
        self._setup_tools()

    @property
    def system_prompt(self) -> str:
        return """You are a RIGOROUS verification agent. Your job is to THOROUGHLY validate all code changes.

## MANDATORY CHECKS (run ALL of these):
1. **Syntax Validation** - Use check_syntax on ALL Python files
2. **Import Check** - Use check_imports to verify all imports resolve
3. **Test Execution** - Use run_tests to run the test suite
4. **Lint Check** - Use run_linter to check code quality
5. **Type Check** - Use run_typecheck for type safety

## VERIFICATION PROCESS:
1. First, check syntax of all changed files (check_syntax)
2. Then verify imports are valid (check_imports)
3. Run the relevant tests (run_tests)
4. Run linter (run_linter)
5. Run type checker (run_typecheck)

## OUTPUT FORMAT:
After running ALL tools, summarize in JSON:
{
  "syntax_valid": true,
  "imports_valid": true,
  "tests_passed": 5,
  "tests_failed": 0,
  "tests_skipped": 1,
  "lint_issues": ["file.py:10: unused import"],
  "type_errors": [],
  "coverage_percent": 85.5,
  "summary": "All checks pass",
  "issues_found": []
}

## IMPORTANT:
- ALWAYS run the tools - don't just describe what you would do
- If ANY check fails, set success=false and list all issues
- Be STRICT - a single failing test means the verification FAILS
- Report SPECIFIC line numbers and file paths for issues
- Suggest CONCRETE fixes for each issue found

## PATH RULES (CRITICAL):
- Use ONLY relative paths like "main.py", "src/utils.py"
- NEVER use absolute paths like /home/... or /tmp/...
- NEVER use ~ or $HOME
- If a file doesn't exist after 2 attempts, report it as missing and move on
- Don't keep retrying the same file path"""

    def _setup_tools(self) -> None:
        """Register tools for the verifier."""
        # Syntax validation - MUST run first
        self.register_tool(
            name="check_syntax",
            description="Validate Python syntax of a file - run this FIRST on all changed files",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Python file path to check"},
                },
                "required": ["path"],
            },
            handler=self._check_syntax,
        )

        # Import validation
        self.register_tool(
            name="check_imports",
            description="Verify all imports in a file can be resolved",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Python file path to check"},
                },
                "required": ["path"],
            },
            handler=self._check_imports,
        )

        # Test execution
        self.register_tool(
            name="run_tests",
            description="Run pytest test suite",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Test path or pattern (default: .)"},
                    "verbose": {"type": "boolean", "description": "Verbose output"},
                    "pattern": {"type": "string", "description": "Filter tests by keyword pattern (-k)"},
                },
                "required": [],
            },
            handler=self._run_tests,
        )

        # Linting
        self.register_tool(
            name="run_linter",
            description="Run code linter (ruff)",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to lint (default: .)"},
                    "fix": {"type": "boolean", "description": "Auto-fix issues"},
                },
                "required": [],
            },
            handler=self._run_linter,
        )

        # Type checking
        self.register_tool(
            name="run_typecheck",
            description="Run type checker (mypy/pyright)",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to check (default: .)"},
                },
                "required": [],
            },
            handler=self._run_typecheck,
        )

        # Read file for manual inspection
        self.register_tool(
            name="read_file",
            description="Read a file to manually inspect code",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                },
                "required": ["path"],
            },
            handler=self._read_file,
        )

    def get_tools(self) -> list[ToolDefinition]:
        """Return verifier-specific tools."""
        return self._tools

    async def _check_syntax(self, path: str) -> str:
        """Check Python syntax of a file."""
        import ast
        from pathlib import Path

        if path in self._failed_paths:
            return f"ERROR: Already tried '{path}' - skip this file."

        try:
            file_path = Path(path)
            # Resolve relative paths against working directory
            if not file_path.is_absolute():
                file_path = self._working_dir / path

            if not file_path.exists():
                # Only reject outside-working-dir paths when file doesn't exist
                try:
                    file_path.resolve().relative_to(self._working_dir)
                except ValueError:
                    return f"ERROR: Path '{path}' is outside working directory. Use relative paths like 'main.py'."

                self._failed_paths.add(path)
                available = [f.name for f in self._working_dir.iterdir() if f.is_file() and f.suffix == ".py"][:10]
                return f"ERROR: File not found: {path}. Python files: {available}"

            if not file_path.suffix == ".py":
                return f"SKIP: Not a Python file: {path}"

            source = file_path.read_text(encoding="utf-8")
            ast.parse(source)
            return f"OK: Syntax valid for {path}"

        except SyntaxError as e:
            return f"SYNTAX ERROR in {path}:\n  Line {e.lineno}: {e.msg}\n  {e.text}"
        except Exception as e:
            return f"ERROR checking {path}: {e}"

    async def _check_imports(self, path: str) -> str:
        """Verify imports in a file can be resolved."""
        import ast
        from pathlib import Path

        if path in self._failed_paths:
            return f"ERROR: Already tried '{path}' - skip this file."

        try:
            file_path = Path(path)
            # Resolve relative paths against working directory
            if not file_path.is_absolute():
                file_path = self._working_dir / path

            if not file_path.exists():
                # Reject outside-working-dir paths when file doesn't exist
                try:
                    file_path.resolve().relative_to(self._working_dir)
                except ValueError:
                    return f"ERROR: Path '{path}' is outside working directory. Use relative paths."

                self._failed_paths.add(path)
                return f"ERROR: File not found: {path}"

            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)

            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)

            # Check if imports resolve
            issues = []
            for module in imports:
                try:
                    __import__(module.split(".")[0])
                except ImportError:
                    issues.append(f"  - Cannot import: {module}")

            if issues:
                return f"IMPORT ISSUES in {path}:\n" + "\n".join(issues)
            return f"OK: All {len(imports)} imports valid in {path}"

        except Exception as e:
            return f"ERROR checking imports in {path}: {e}"

    async def _run_tests(self, path: str = ".", verbose: bool = False, pattern: str = "") -> str:
        """Run pytest tests."""
        return f"[Would run: pytest {path} {'-v' if verbose else ''} {f'-k {pattern}' if pattern else ''}]"

    async def _run_linter(self, path: str = ".", fix: bool = False) -> str:
        """Run ruff linter."""
        return f"[Would run: ruff check {path} {'--fix' if fix else ''}]"

    async def _run_typecheck(self, path: str = ".") -> str:
        """Run type checker."""
        return f"[Would run: mypy {path}]"

    async def _read_file(self, path: str) -> str:
        """Read a file for inspection."""
        from pathlib import Path

        # Check if we already tried this path
        if path in self._failed_paths:
            return f"ERROR: Already tried '{path}' - file does not exist. Skip this file."

        try:
            file_path = Path(path)
            # Resolve relative paths against working directory
            if not file_path.is_absolute():
                file_path = self._working_dir / path

            if not file_path.exists():
                # Reject outside-working-dir paths when file doesn't exist
                try:
                    file_path.resolve().relative_to(self._working_dir)
                except ValueError:
                    return f"ERROR: Path '{path}' is outside working directory. Use relative paths like 'main.py'."

                self._failed_paths.add(path)
                # List available files to help the LLM
                available = [f.name for f in self._working_dir.iterdir() if f.is_file()][:10]
                return f"ERROR: File not found: {path}. Available files: {available}"

            content = file_path.read_text(encoding="utf-8", errors="replace")

            # Truncate if too long
            if len(content) > 5000:
                content = content[:5000] + "\n... (truncated)"

            return f"Contents of {path}:\n```\n{content}\n```"
        except Exception as e:
            return f"ERROR reading {path}: {e}"

    def inject_tools(self, code_tools: Any, sandbox: Any = None) -> None:
        """Inject real tool implementations."""
        if hasattr(code_tools, "run_tests"):
            self._tool_handlers["run_tests"] = code_tools.run_tests
        if hasattr(code_tools, "run_linter"):
            self._tool_handlers["run_linter"] = code_tools.run_linter
        if hasattr(code_tools, "run_typecheck"):
            self._tool_handlers["run_typecheck"] = code_tools.run_typecheck

    async def process_response(
        self, response: CompletionResponse, tool_outputs: list[str]
    ) -> AgentResult:
        """Parse verification results."""
        content = response.content

        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)

                passed = data.get("tests_passed") or 0
                failed = data.get("tests_failed") or 0
                skipped = data.get("tests_skipped") or 0
                lint_issues = data.get("lint_issues") or []
                type_errors = data.get("type_errors") or []

                # Ensure lists are actually lists (LLM might return strings)
                if isinstance(lint_issues, str):
                    lint_issues = [lint_issues] if lint_issues else []
                if isinstance(type_errors, str):
                    type_errors = [type_errors] if type_errors else []

                success = failed == 0 and len(type_errors) == 0

                return AgentResult(
                    success=success,
                    output=content,
                    data={
                        "tests_passed": passed,
                        "tests_failed": failed,
                        "tests_skipped": skipped,
                        "lint_issues": lint_issues,
                        "type_errors": type_errors,
                        "coverage": data.get("coverage_percent"),
                    },
                    tokens_used=response.total_tokens,
                    summary_for_next_agent=(
                        f"Tests: {passed} passed, {failed} failed. "
                        f"Lint: {len(lint_issues)} issues. Types: {len(type_errors)} errors."
                    ),
                )

        except (json.JSONDecodeError, KeyError):
            pass

        # Improved fallback: use heuristics to infer success from tool outputs
        content_lower = content.lower() if content else ""
        tool_output_str = "\n".join(tool_outputs).lower()

        # Heuristic 1: Tests passed without failures
        tests_ok = (
            ("passed" in tool_output_str or "passed" in content_lower)
            and "failed" not in tool_output_str
            and "failure" not in tool_output_str
        )

        # Heuristic 2: No errors mentioned (or explicitly "0 errors")
        no_errors = (
            "0 errors" in content_lower
            or "0 errors" in tool_output_str
            or (
                "error" not in content_lower
                and "error" not in tool_output_str
            )
        )

        # Heuristic 3: Explicit success indicators
        explicit_success = (
            "all checks pass" in content_lower
            or "verification successful" in content_lower
            or "syntax valid" in tool_output_str
        )

        # Infer success: tests OK and no errors, or explicit success
        inferred_success = (tests_ok and no_errors) or explicit_success

        # Extract approximate counts from tool outputs
        passed_count = tool_output_str.count(" passed")
        failed_count = tool_output_str.count(" failed")

        return AgentResult(
            success=inferred_success,
            output=content,
            data={
                "tool_outputs": tool_outputs,
                "tests_passed": max(passed_count, 0),
                "tests_failed": max(failed_count, 0),
                "inferred_from_heuristics": True,
            },
            tokens_used=response.total_tokens,
            summary_for_next_agent=(
                f"Verification {'passed' if inferred_success else 'failed'} "
                f"(heuristic: tests_ok={tests_ok}, no_errors={no_errors})"
            ),
        )

    async def verify_changes(
        self, context: AgentContext, changed_files: list[str], max_retries: int = 2
    ) -> VerificationResult:
        """Verify changes to specific files with retry logic.

        Args:
            context: Agent context
            changed_files: Files to verify
            max_retries: Number of retries for recoverable failures

        Returns:
            VerificationResult with test/lint/type results
        """
        request = f"Verify changes to: {', '.join(changed_files)}"

        last_result = None
        for attempt in range(1, max_retries + 1):
            result = await self.run(context, request, max_tool_calls=self.default_max_tool_calls)

            # Handle None result (LLM failure, timeout, etc.)
            if result is None:
                import logging
                logging.getLogger(__name__).warning(
                    "Verification attempt %d returned None, retrying...", attempt
                )
                continue

            last_result = result

            if result.success:
                break

            # Check if failure is recoverable (timeout, rate limit, etc.)
            if attempt < max_retries and self._is_recoverable_failure(result):
                import logging
                logging.getLogger(__name__).info(
                    "Verification attempt %d failed (recoverable), retrying...", attempt
                )
                import asyncio
                await asyncio.sleep(1.0 * attempt)  # Exponential-ish backoff
                continue

            # Non-recoverable or last attempt
            break

        # Handle case where all attempts returned None
        if last_result is None:
            return VerificationResult(
                success=False,
                tests_passed=0,
                tests_failed=0,
                tests_skipped=0,
                test_results=[],
                lint_issues=[],
                type_errors=[],
                coverage_percent=None,
                summary="Verification failed: No response from agent after retries",
            )

        result = last_result
        data = result.data
        test_results = [
            SingleTestResult(name=f"test_{i}", passed=True)
            for i in range(data.get("tests_passed", 0))
        ] + [
            SingleTestResult(name=f"failed_{i}", passed=False)
            for i in range(data.get("tests_failed", 0))
        ]

        return VerificationResult(
            success=result.success,
            tests_passed=data.get("tests_passed", 0),
            tests_failed=data.get("tests_failed", 0),
            tests_skipped=data.get("tests_skipped", 0),
            test_results=test_results,
            lint_issues=data.get("lint_issues", []),
            type_errors=data.get("type_errors", []),
            coverage_percent=data.get("coverage"),
            summary=result.summary_for_next_agent,
        )

    def _is_recoverable_failure(self, result: AgentResult) -> bool:
        """Check if a failure is recoverable (worth retrying)."""
        output_lower = result.output.lower() if result.output else ""

        # Recoverable: timeouts, rate limits, temporary network issues
        recoverable_patterns = [
            "timeout",
            "timed out",
            "rate limit",
            "429",
            "temporary",
            "connection refused",
            "connection reset",
            "network",
        ]

        return any(pattern in output_lower for pattern in recoverable_patterns)
