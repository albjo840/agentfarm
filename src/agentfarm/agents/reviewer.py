from __future__ import annotations

"""ReviewerAgent - reviews code changes for quality and correctness."""

import json
from typing import Any

from agentfarm.agents.base import AgentContext, AgentResult, BaseAgent
from agentfarm.models.schemas import ReviewComment, ReviewResult
from agentfarm.providers.base import CompletionResponse, LLMProvider, ToolDefinition


class ReviewerAgent(BaseAgent):
    """Agent responsible for code review.

    Reviews code changes for quality, security, and adherence to patterns.
    """

    name = "ReviewerAgent"
    description = "Reviews code for quality and correctness"

    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider)
        self._setup_tools()

    @property
    def system_prompt(self) -> str:
        return """You are a code review agent. Your role is to:
1. Review code changes for correctness
2. Check for security issues
3. Verify adherence to project patterns
4. Provide constructive feedback

Output JSON:
{
  "approved": true|false,
  "comments": [
    {"file": "path.py", "line": 42, "severity": "warning", "message": "Consider..."}
  ],
  "suggestions": ["suggestion1", "suggestion2"],
  "summary": "Overall assessment"
}

Severity levels: info, warning, error

Guidelines:
- Focus on correctness and security
- Be constructive, not nitpicky
- Approve if no blocking issues
- Suggest improvements for next iteration"""

    def _setup_tools(self) -> None:
        """Register tools for the reviewer."""
        self.register_tool(
            name="read_file",
            description="Read file to review",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"],
            },
            handler=self._read_file,
        )

        self.register_tool(
            name="get_diff",
            description="Get diff of changes",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "base": {"type": "string", "description": "Base ref (default: HEAD)"},
                },
                "required": [],
            },
            handler=self._get_diff,
        )

        self.register_tool(
            name="add_comment",
            description="Add a review comment",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path"},
                    "line": {"type": "integer", "description": "Line number"},
                    "message": {"type": "string", "description": "Comment message"},
                    "severity": {
                        "type": "string",
                        "enum": ["info", "warning", "error"],
                        "description": "Severity level",
                    },
                },
                "required": ["file", "message", "severity"],
            },
            handler=self._add_comment,
        )

    def get_tools(self) -> list[ToolDefinition]:
        """Return reviewer-specific tools."""
        return self._tools

    async def _read_file(self, path: str) -> str:
        """Read file - placeholder."""
        return f"[Contents of {path}]"

    async def _get_diff(self, path: str = ".", base: str = "HEAD") -> str:
        """Get diff - placeholder."""
        return f"[Diff for {path} against {base}]"

    async def _add_comment(
        self, file: str, message: str, severity: str, line: int | None = None
    ) -> str:
        """Add comment - placeholder."""
        return f"[Added {severity} comment on {file}:{line or 'general'}]"

    def inject_tools(self, file_tools: Any, git_tools: Any) -> None:
        """Inject real tool implementations."""
        self._tool_handlers["read_file"] = file_tools.read_file
        self._tool_handlers["get_diff"] = git_tools.get_diff
        # add_comment might store comments for later

    async def process_response(
        self, response: CompletionResponse, tool_outputs: list[str]
    ) -> AgentResult:
        """Parse review results."""
        content = response.content

        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)

                comments = [
                    ReviewComment(
                        file=c["file"],
                        line=c.get("line"),
                        severity=c.get("severity", "info"),
                        message=c["message"],
                    )
                    for c in data.get("comments", [])
                ]

                approved = data.get("approved", False)
                suggestions = data.get("suggestions", [])

                # Count by severity
                errors = sum(1 for c in comments if c.severity == "error")
                warnings = sum(1 for c in comments if c.severity == "warning")

                return AgentResult(
                    success=approved,
                    output=content,
                    data={
                        "approved": approved,
                        "comments": [c.model_dump() for c in comments],
                        "suggestions": suggestions,
                        "errors": errors,
                        "warnings": warnings,
                    },
                    tokens_used=response.total_tokens,
                    summary_for_next_agent=(
                        f"Review: {'Approved' if approved else 'Changes requested'}. "
                        f"{errors} errors, {warnings} warnings."
                    ),
                )

        except (json.JSONDecodeError, KeyError):
            pass

        return AgentResult(
            success=False,
            output=content,
            data={"tool_outputs": tool_outputs},
            tokens_used=response.total_tokens,
            summary_for_next_agent="Review completed, see details",
        )

    async def review_changes(
        self, context: AgentContext, changed_files: list[str], diff: str | None = None
    ) -> ReviewResult:
        """Review specific file changes."""
        request = f"Review changes to: {', '.join(changed_files)}"
        if diff:
            request += f"\n\nDiff:\n{diff}"

        result = await self.run(context, request)
        data = result.data

        comments = [ReviewComment(**c) for c in data.get("comments", [])]

        return ReviewResult(
            approved=data.get("approved", False),
            comments=comments,
            summary=result.summary_for_next_agent,
            suggestions=data.get("suggestions", []),
        )
