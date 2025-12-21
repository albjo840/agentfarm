from __future__ import annotations

"""PlannerAgent - breaks down tasks into executable steps."""

import json
from typing import Any

from agentfarm.agents.base import AgentContext, AgentResult, BaseAgent
from agentfarm.models.schemas import PlanStep, TaskPlan
from agentfarm.providers.base import CompletionResponse, LLMProvider, ToolDefinition


class PlannerAgent(BaseAgent):
    """Agent responsible for task planning and breakdown.

    Takes a high-level task and produces a structured plan with
    atomic, verifiable steps. Uses minimal context to reduce tokens.
    """

    name = "PlannerAgent"
    description = "Plans tasks and breaks them into executable steps"

    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider)
        self._setup_tools()

    @property
    def system_prompt(self) -> str:
        return """You are a task planning agent. Create executable plans quickly and efficiently.

IMPORTANT: Generate your plan JSON IMMEDIATELY without excessive exploration.
Only use tools when you NEED specific information about existing code.
After 1-2 tool calls at most, output your plan.

Output your plan as JSON with this structure:
{
  "summary": "Brief approach description (1-2 sentences)",
  "steps": [
    {
      "id": 1,
      "description": "What this step does",
      "agent": "ExecutorAgent|VerifierAgent|ReviewerAgent",
      "tools": ["tool1", "tool2"],
      "dependencies": []
    }
  ]
}

RULES:
- Keep plans SHORT: 3-5 steps typical, 8 steps maximum
- Be decisive - don't overthink
- Executor = code changes, Verifier = testing, Reviewer = code review
- Output JSON directly - no markdown code blocks needed
- If unsure about project structure, make reasonable assumptions

After reading this prompt, generate your plan JSON immediately."""

    def _setup_tools(self) -> None:
        """Register tools for the planner."""
        self.register_tool(
            name="read_file",
            description="Read contents of a file to understand existing code",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"}
                },
                "required": ["path"],
            },
            handler=self._read_file,
        )

        self.register_tool(
            name="list_directory",
            description="List files in a directory to understand project structure",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path"}
                },
                "required": ["path"],
            },
            handler=self._list_directory,
        )

        self.register_tool(
            name="search_code",
            description="Search for patterns in code",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern"},
                    "path": {"type": "string", "description": "Directory to search in"},
                },
                "required": ["pattern"],
            },
            handler=self._search_code,
        )

    def get_tools(self) -> list[ToolDefinition]:
        """Return planner-specific tools."""
        return self._tools

    async def _read_file(self, path: str) -> str:
        """Read file contents - placeholder, inject real implementation."""
        return f"[File contents of {path} would be here]"

    async def _list_directory(self, path: str) -> str:
        """List directory - placeholder, inject real implementation."""
        return f"[Directory listing of {path} would be here]"

    async def _search_code(self, pattern: str, path: str = ".") -> str:
        """Search code - placeholder, inject real implementation."""
        return f"[Search results for '{pattern}' in {path} would be here]"

    def inject_file_tools(self, file_tools: Any) -> None:
        """Inject real file tool implementations."""
        self._tool_handlers["read_file"] = file_tools.read_file
        self._tool_handlers["list_directory"] = file_tools.list_directory
        self._tool_handlers["search_code"] = file_tools.search_code

    async def process_response(
        self, response: CompletionResponse, tool_outputs: list[str]
    ) -> AgentResult:
        """Parse the planning response into a TaskPlan."""
        content = response.content

        # Try to extract JSON from the response
        try:
            # Find JSON in the response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)

                steps = [
                    PlanStep(
                        id=s.get("id", i + 1),
                        description=s["description"],
                        agent=s["agent"],
                        tools=s.get("tools", []),
                        dependencies=s.get("dependencies", []),
                    )
                    for i, s in enumerate(data.get("steps", []))
                ]

                plan = TaskPlan(
                    task_description="",  # Set by orchestrator
                    summary=data.get("summary", ""),
                    steps=steps,
                )

                return AgentResult(
                    success=True,
                    output=content,
                    data={"plan": plan.model_dump()},
                    tokens_used=response.total_tokens,
                    summary_for_next_agent=f"Plan created with {len(steps)} steps: {plan.summary}",
                )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return AgentResult(
                success=False,
                output=content,
                data={"error": str(e)},
                tokens_used=response.total_tokens,
                summary_for_next_agent=f"Planning failed: {e}",
            )

        return AgentResult(
            success=False,
            output=content,
            data={"error": "Could not parse plan from response"},
            tokens_used=response.total_tokens,
            summary_for_next_agent="Planning failed: could not parse response",
        )

    async def create_plan(self, context: AgentContext, task: str) -> TaskPlan | None:
        """Convenience method to create a plan and return it directly.

        Uses a low tool call limit (3) to encourage fast planning.
        """
        result = await self.run(context, task, max_tool_calls=3)
        if result.success and "plan" in result.data:
            plan_data = result.data["plan"]
            plan = TaskPlan(**plan_data)
            plan.task_description = task
            return plan
        return None
