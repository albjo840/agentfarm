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

    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider)
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
- Suggest CONCRETE fixes for each issue found"""

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
                    "keywords": {"type": "string", "description": "Filter tests by keyword (-k)"},
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

        try:
            file_path = Path(path)
            if not file_path.exists():
                return f"ERROR: File not found: {path}"

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

        try:
            file_path = Path(path)
            if not file_path.exists():
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

    async def _run_tests(self, path: str = ".", verbose: bool = False, keywords: str = "") -> str:
        """Run pytest tests."""
        return f"[Would run: pytest {path} {'-v' if verbose else ''} {f'-k {keywords}' if keywords else ''}]"

    async def _run_linter(self, path: str = ".", fix: bool = False) -> str:
        """Run ruff linter."""
        return f"[Would run: ruff check {path} {'--fix' if fix else ''}]"

    async def _run_typecheck(self, path: str = ".") -> str:
        """Run type checker."""
        return f"[Would run: mypy {path}]"

    async def _read_file(self, path: str) -> str:
        """Read a file for inspection."""
        from pathlib import Path

        try:
            file_path = Path(path)
            if not file_path.exists():
                return f"ERROR: File not found: {path}"

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

                passed = data.get("tests_passed", 0)
                failed = data.get("tests_failed", 0)
                skipped = data.get("tests_skipped", 0)
                lint_issues = data.get("lint_issues", [])
                type_errors = data.get("type_errors", [])

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

        # Fallback
        return AgentResult(
            success=False,
            output=content,
            data={"tool_outputs": tool_outputs},
            tokens_used=response.total_tokens,
            summary_for_next_agent="Verification completed, see details",
        )

    async def verify_changes(
        self, context: AgentContext, changed_files: list[str]
    ) -> VerificationResult:
        """Verify changes to specific files."""
        request = f"Verify changes to: {', '.join(changed_files)}"
        result = await self.run(context, request)

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
