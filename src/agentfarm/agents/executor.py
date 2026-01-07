from __future__ import annotations

"""ExecutorAgent - implements code changes."""

import json
from typing import Any

from agentfarm.agents.base import AgentContext, AgentResult, BaseAgent
from agentfarm.models.schemas import ExecutionResult, FileChange
from agentfarm.providers.base import CompletionResponse, LLMProvider, ToolDefinition


class ExecutorAgent(BaseAgent):
    """Agent responsible for executing code changes.

    Takes a single step from the plan and implements it.
    Operates in a sandboxed environment for safety.
    """

    name = "ExecutorAgent"
    description = "Executes code changes safely"

    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider)
        self._setup_tools()

    @property
    def system_prompt(self) -> str:
        return """You are a code execution agent. Your role is to:
1. Implement the requested code change using the available tools
2. Make minimal, focused changes
3. Follow existing code patterns

IMPORTANT: Use the write_file tool to create new files. Use edit_file to modify existing files.
Do NOT just describe what to do - actually call the tools to make changes.

Guidelines:
- One logical change at a time
- Preserve existing style
- Add minimal necessary code
- No unnecessary refactoring
- Always use tools to make file changes"""

    def _setup_tools(self) -> None:
        """Register tools for the executor."""
        self.register_tool(
            name="read_file",
            description="Read file contents before editing",
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
            name="write_file",
            description="Create or overwrite a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path", "content"],
            },
            handler=self._write_file,
        )

        self.register_tool(
            name="edit_file",
            description="Edit a specific part of a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "old_content": {"type": "string", "description": "Content to replace"},
                    "new_content": {"type": "string", "description": "New content"},
                },
                "required": ["path", "old_content", "new_content"],
            },
            handler=self._edit_file,
        )

        self.register_tool(
            name="run_in_sandbox",
            description="Run code in isolated Docker sandbox",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds"},
                },
                "required": ["command"],
            },
            handler=self._run_in_sandbox,
        )

    def get_tools(self) -> list[ToolDefinition]:
        """Return executor-specific tools."""
        return self._tools

    async def _read_file(self, path: str) -> str:
        """Read file - placeholder."""
        return f"[Contents of {path}]"

    async def _write_file(self, path: str, content: str) -> str:
        """Write file - placeholder."""
        return f"[Wrote {len(content)} bytes to {path}]"

    async def _edit_file(self, path: str, old_content: str, new_content: str) -> str:
        """Edit file - placeholder."""
        return f"[Edited {path}]"

    async def _run_in_sandbox(self, command: str, timeout: int = 30) -> str:
        """Run in sandbox - placeholder."""
        return f"[Ran '{command}' with timeout {timeout}s]"

    def inject_tools(self, file_tools: Any, sandbox: Any) -> None:
        """Inject real tool implementations."""
        self._tool_handlers["read_file"] = file_tools.read_file
        self._tool_handlers["write_file"] = file_tools.write_file
        self._tool_handlers["edit_file"] = file_tools.edit_file
        self._tool_handlers["run_in_sandbox"] = sandbox.run

    async def process_response(
        self, response: CompletionResponse, tool_outputs: list[str]
    ) -> AgentResult:
        """Parse execution results."""
        content = response.content
        files_changed: list[FileChange] = []

        # Try to extract JSON
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)

                for f in data.get("files_changed", []):
                    files_changed.append(
                        FileChange(
                            path=f["path"],
                            action=f.get("action", "edit"),
                            diff=f.get("description"),
                        )
                    )

                summary = data.get("summary", "Changes executed")

                return AgentResult(
                    success=True,
                    output=content,
                    data={
                        "files_changed": [fc.model_dump() for fc in files_changed],
                        "tool_outputs": tool_outputs,
                    },
                    tokens_used=response.total_tokens,
                    summary_for_next_agent=f"Executed: {summary}. Files: {[fc.path for fc in files_changed]}",
                )

        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback: parse from tool outputs
        return AgentResult(
            success=len(tool_outputs) > 0,
            output=content,
            data={"tool_outputs": tool_outputs},
            tokens_used=response.total_tokens,
            summary_for_next_agent=f"Executed with {len(tool_outputs)} tool calls",
        )

    async def execute_step(
        self, context: AgentContext, step_description: str, step_id: int
    ) -> ExecutionResult:
        """Execute a single step and return structured result."""
        result = await self.run(context, step_description)

        files_changed = [
            FileChange(**fc) for fc in result.data.get("files_changed", [])
        ]

        return ExecutionResult(
            success=result.success,
            step_id=step_id,
            files_changed=files_changed,
            output=result.summary_for_next_agent,
            error=None if result.success else result.output,
        )
