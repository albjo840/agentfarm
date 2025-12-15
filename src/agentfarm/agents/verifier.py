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
        return """You are a verification agent. Your role is to:
1. Run appropriate tests for the changes
2. Check code quality (linting, formatting)
3. Verify type correctness
4. Report results clearly

Output JSON:
{
  "tests_passed": 5,
  "tests_failed": 0,
  "tests_skipped": 1,
  "lint_issues": ["issue1", "issue2"],
  "type_errors": [],
  "coverage_percent": 85.5,
  "summary": "All tests pass, minor lint issues"
}

Guidelines:
- Run tests related to changed files
- Report all failures clearly
- Suggest fixes for failures
- Be thorough but efficient"""

    def _setup_tools(self) -> None:
        """Register tools for the verifier."""
        self.register_tool(
            name="run_tests",
            description="Run test suite",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Test path or pattern"},
                    "verbose": {"type": "boolean", "description": "Verbose output"},
                },
                "required": [],
            },
            handler=self._run_tests,
        )

        self.register_tool(
            name="run_linter",
            description="Run code linter (ruff)",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to lint"},
                    "fix": {"type": "boolean", "description": "Auto-fix issues"},
                },
                "required": [],
            },
            handler=self._run_linter,
        )

        self.register_tool(
            name="run_typecheck",
            description="Run type checker (mypy/pyright)",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to check"},
                },
                "required": [],
            },
            handler=self._run_typecheck,
        )

    def get_tools(self) -> list[ToolDefinition]:
        """Return verifier-specific tools."""
        return self._tools

    async def _run_tests(self, path: str = ".", verbose: bool = False) -> str:
        """Run tests - placeholder."""
        return "[Test results would be here]"

    async def _run_linter(self, path: str = ".", fix: bool = False) -> str:
        """Run linter - placeholder."""
        return "[Lint results would be here]"

    async def _run_typecheck(self, path: str = ".") -> str:
        """Run type checker - placeholder."""
        return "[Type check results would be here]"

    def inject_tools(self, code_tools: Any, sandbox: Any) -> None:
        """Inject real tool implementations."""
        self._tool_handlers["run_tests"] = code_tools.run_tests
        self._tool_handlers["run_linter"] = code_tools.run_linter
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
