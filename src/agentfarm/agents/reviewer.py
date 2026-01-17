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

    def __init__(self, provider: LLMProvider, working_dir: str = ".") -> None:
        super().__init__(provider)
        self._working_dir = working_dir
        self._setup_tools()

    @property
    def system_prompt(self) -> str:
        return """You are a RIGOROUS code review agent. Your job is to thoroughly review ALL code changes.

## MANDATORY REVIEW CHECKLIST (check ALL items):

### 1. CORRECTNESS
- Does the code do what it's supposed to do?
- Are there any logical errors?
- Are edge cases handled?
- Is error handling adequate?

### 2. SECURITY (CRITICAL)
- No hardcoded credentials or API keys
- No SQL injection vulnerabilities
- No XSS vulnerabilities
- No path traversal vulnerabilities
- Input validation present
- Proper authentication/authorization

### 3. CODE QUALITY
- Follows existing code patterns
- Proper naming conventions
- No code duplication
- Functions/methods not too long (< 50 lines)
- Single responsibility principle

### 4. BEST PRACTICES
- Type hints present
- Docstrings for public functions
- No unused imports
- No unused variables
- Async/await used correctly

### 5. PERFORMANCE
- No obvious N+1 query patterns
- No unnecessary loops
- Efficient data structures

## REVIEW PROCESS:
1. Use read_file to examine ALL changed files
2. Use check_security to scan for security issues
3. Use check_patterns to verify code patterns
4. Add comments using add_comment for each issue found

## OUTPUT FORMAT:
{
  "approved": false,  // ONLY true if NO errors found
  "checklist": {
    "correctness": true,
    "security": true,
    "code_quality": true,
    "best_practices": true,
    "performance": true
  },
  "comments": [
    {"file": "path.py", "line": 42, "severity": "error", "message": "Security: hardcoded password"}
  ],
  "suggestions": ["Add input validation for user data"],
  "summary": "Changes requested: 1 security issue found"
}

## SEVERITY RULES:
- error: Blocks approval (security issues, bugs, crashes)
- warning: Should fix but not blocking
- info: Nice-to-have improvements

**BE STRICT** - If you find ANY error-level issue, set approved=false"""

    def _setup_tools(self) -> None:
        """Register tools for the reviewer."""
        self.register_tool(
            name="read_file",
            description="Read a file to review its contents",
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
            description="Get git diff of changes",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (optional)"},
                    "base": {"type": "string", "description": "Base ref (default: HEAD)"},
                },
                "required": [],
            },
            handler=self._get_diff,
        )

        self.register_tool(
            name="check_security",
            description="Scan file for security vulnerabilities",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to scan"},
                },
                "required": ["path"],
            },
            handler=self._check_security,
        )

        self.register_tool(
            name="check_patterns",
            description="Check code against project patterns and best practices",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to check"},
                },
                "required": ["path"],
            },
            handler=self._check_patterns,
        )

        self.register_tool(
            name="add_comment",
            description="Add a review comment for an issue found",
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
        """Read a file for review."""
        from pathlib import Path

        try:
            # Handle both absolute and relative paths
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = Path(self._working_dir) / path

            if not file_path.exists():
                return f"ERROR: File not found: {path}"

            content = file_path.read_text(encoding="utf-8", errors="replace")

            # Add line numbers for easier reference
            lines = content.split("\n")
            numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))

            if len(numbered) > 8000:
                numbered = numbered[:8000] + "\n... (truncated)"

            return f"Contents of {path} ({len(lines)} lines):\n{numbered}"
        except Exception as e:
            return f"ERROR reading {path}: {e}"

    async def _get_diff(self, path: str = ".", base: str = "HEAD") -> str:
        """Get git diff."""
        return f"[Would run: git diff {base} -- {path}]"

    async def _check_security(self, path: str) -> str:
        """Scan file for common security vulnerabilities."""
        from pathlib import Path
        import re

        try:
            # Handle both absolute and relative paths
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = Path(self._working_dir) / path

            if not file_path.exists():
                return f"ERROR: File not found: {path}"

            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")
            issues = []

            # Security patterns to check
            patterns = [
                (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password"),
                (r'api_key\s*=\s*["\'][^"\']+["\']', "Hardcoded API key"),
                (r'secret\s*=\s*["\'][^"\']+["\']', "Hardcoded secret"),
                (r'eval\s*\(', "Use of eval() - potential code injection"),
                (r'exec\s*\(', "Use of exec() - potential code injection"),
                (r'os\.system\s*\(', "Use of os.system() - prefer subprocess"),
                (r'shell\s*=\s*True', "shell=True - potential command injection"),
                (r'\.format\s*\([^)]*request', "String formatting with request data - potential injection"),
                (r'%s.*request', "String interpolation with request data"),
                (r'pickle\.loads?\s*\(', "Pickle deserialization - potential security risk"),
                (r'yaml\.load\s*\([^)]*Loader\s*=\s*None', "Unsafe YAML loading"),
                (r'__import__\s*\(', "Dynamic import - potential risk"),
            ]

            for i, line in enumerate(lines, 1):
                for pattern, description in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        issues.append(f"  Line {i}: {description}")
                        issues.append(f"    {line.strip()[:80]}")

            if issues:
                return f"SECURITY ISSUES in {path}:\n" + "\n".join(issues)
            return f"OK: No obvious security issues in {path}"

        except Exception as e:
            return f"ERROR checking security in {path}: {e}"

    async def _check_patterns(self, path: str) -> str:
        """Check code against best practices."""
        from pathlib import Path
        import ast

        try:
            # Handle both absolute and relative paths
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = Path(self._working_dir) / path

            if not file_path.exists():
                return f"ERROR: File not found: {path}"

            if not path.endswith(".py"):
                return f"SKIP: Not a Python file: {path}"

            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            issues = []

            # Parse AST for analysis
            try:
                tree = ast.parse(content)
            except SyntaxError:
                return f"ERROR: Cannot parse {path} - syntax error"

            # Check function lengths
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_lines = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
                    if func_lines > 50:
                        issues.append(f"  Line {node.lineno}: Function '{node.name}' is {func_lines} lines (max 50)")

                    # Check for docstring
                    if not ast.get_docstring(node):
                        issues.append(f"  Line {node.lineno}: Function '{node.name}' missing docstring")

                    # Check for type hints
                    if not node.returns:
                        issues.append(f"  Line {node.lineno}: Function '{node.name}' missing return type hint")

            # Check for common anti-patterns
            for i, line in enumerate(lines, 1):
                # Bare except
                if "except:" in line and "except Exception" not in line:
                    issues.append(f"  Line {i}: Bare 'except:' - catch specific exceptions")

                # TODO/FIXME without ticket
                if "TODO" in line or "FIXME" in line:
                    if not any(c in line for c in ["#", "ticket", "issue", "JIRA"]):
                        issues.append(f"  Line {i}: TODO/FIXME without reference")

                # Print statements in production code
                if line.strip().startswith("print(") and "debug" not in path.lower():
                    issues.append(f"  Line {i}: print() in production code - use logging")

            if issues:
                return f"CODE PATTERN ISSUES in {path}:\n" + "\n".join(issues[:20])  # Max 20 issues
            return f"OK: Code follows best practices in {path}"

        except Exception as e:
            return f"ERROR checking patterns in {path}: {e}"

    async def _add_comment(
        self, file: str, message: str, severity: str, line: int | None = None
    ) -> str:
        """Add a review comment."""
        location = f"{file}:{line}" if line else file
        return f"[COMMENT {severity.upper()}] {location}: {message}"

    def inject_tools(self, file_tools: Any = None, git_tools: Any = None) -> None:
        """Inject real tool implementations."""
        if file_tools and hasattr(file_tools, "read_file"):
            self._tool_handlers["read_file"] = file_tools.read_file
        if git_tools and hasattr(git_tools, "get_diff"):
            self._tool_handlers["get_diff"] = git_tools.get_diff

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

        except (json.JSONDecodeError, KeyError) as e:
            # JSON parsing failed - try to extract approval from text
            content_lower = content.lower()

            # Heuristic: If review mentions "approved" positively, consider it approved
            approved = False
            if "approved" in content_lower:
                if "not approved" not in content_lower and "changes requested" not in content_lower:
                    approved = "approved: true" in content_lower or '"approved": true' in content_lower

            return AgentResult(
                success=approved,
                output=content,
                data={
                    "tool_outputs": tool_outputs,
                    "parse_error": str(e),
                    "approved": approved,
                },
                tokens_used=response.total_tokens,
                summary_for_next_agent=f"Review: {'Approved' if approved else 'Changes requested'} (JSON parse fallback)",
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
