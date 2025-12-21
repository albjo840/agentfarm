from __future__ import annotations

"""OrchestratorAgent - LLM-driven coordinator that dynamically controls other agents."""

import json
from typing import Any

from agentfarm.agents.base import AgentContext, AgentResult, BaseAgent
from agentfarm.agents.executor import ExecutorAgent
from agentfarm.agents.planner import PlannerAgent
from agentfarm.agents.reviewer import ReviewerAgent
from agentfarm.agents.ux_designer import UXDesignerAgent
from agentfarm.agents.verifier import VerifierAgent
from agentfarm.memory.base import MemoryManager
from agentfarm.models.schemas import WorkflowResult
from agentfarm.providers.base import CompletionResponse, LLMProvider, ToolDefinition


class OrchestratorAgent(BaseAgent):
    """LLM-driven orchestrator that coordinates worker agents.

    Unlike the hardcoded Orchestrator class, this agent uses an LLM to:
    - Decide which agents to call and in what order
    - Interpret results and make dynamic decisions
    - Handle errors and adjust strategy
    - Maintain workflow state through memory
    """

    name = "OrchestratorAgent"
    description = "Coordinates worker agents to complete complex tasks"

    def __init__(
        self,
        provider: LLMProvider,
        memory: MemoryManager | None = None,
        working_dir: str = ".",
        use_multi_provider: bool = True,
    ) -> None:
        super().__init__(provider)
        self.working_dir = working_dir
        self.memory = memory

        # Initialize worker agents with optimal providers
        if use_multi_provider:
            from agentfarm.multi_provider import create_provider_for_agent
            self._planner = PlannerAgent(create_provider_for_agent("planner"))
            self._executor = ExecutorAgent(create_provider_for_agent("executor"))
            self._verifier = VerifierAgent(create_provider_for_agent("verifier"))
            self._reviewer = ReviewerAgent(create_provider_for_agent("reviewer"))
            self._ux_designer = UXDesignerAgent(create_provider_for_agent("designer"))
        else:
            # Use single provider for all agents
            self._planner = PlannerAgent(provider)
            self._executor = ExecutorAgent(provider)
            self._verifier = VerifierAgent(provider)
            self._reviewer = ReviewerAgent(provider)
            self._ux_designer = UXDesignerAgent(provider)

        # Store results from agent calls
        self._workflow_state: dict[str, Any] = {
            "plan": None,
            "execution_results": [],
            "verification": None,
            "review": None,
            "ux_design": None,
        }

        # Register orchestrator tools
        self._register_orchestrator_tools()

    @property
    def system_prompt(self) -> str:
        """Load system prompt from prompts module or return default."""
        try:
            from agentfarm.prompts import orchestrator_prompt
            return orchestrator_prompt.SYSTEM_PROMPT
        except ImportError:
            return self._default_system_prompt()

    def _default_system_prompt(self) -> str:
        return """You are the OrchestratorAgent, responsible for coordinating a team of specialized agents to complete software engineering tasks.

## Your Role
You analyze tasks and dynamically decide which agents to call and in what order. You interpret results and adjust your strategy based on outcomes.

## Available Agents (via tools)
1. **PlannerAgent** (call_planner) - Creates detailed task plans with steps
2. **ExecutorAgent** (call_executor) - Implements code changes
3. **VerifierAgent** (call_verifier) - Runs tests, linting, type checking
4. **ReviewerAgent** (call_reviewer) - Reviews code quality

## Memory Tools
- **store_memory** - Store important information for later
- **recall_memory** - Retrieve stored information
- **get_workflow_state** - Get current workflow progress

## Guidelines
1. Start by understanding the task - call PlannerAgent first for complex tasks
2. Execute steps methodically - call ExecutorAgent for each implementation step
3. Verify after changes - call VerifierAgent to ensure quality
4. Review before completing - call ReviewerAgent for final quality check
5. Use memory to track progress and learnings
6. If an agent fails, analyze the error and decide: retry, adjust approach, or escalate

## Response Format
After completing the workflow, provide a summary with:
- What was accomplished
- Files changed
- Test results
- Any issues or suggestions

Always explain your reasoning before calling an agent."""

    def _register_orchestrator_tools(self) -> None:
        """Register tools for calling worker agents."""
        # Call Planner
        self.register_tool(
            name="call_planner",
            description="Call PlannerAgent to create a task plan. Use this first for complex tasks.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description to plan",
                    },
                    "context_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Relevant files for context",
                    },
                },
                "required": ["task"],
            },
            handler=self._call_planner,
        )

        # Call Executor
        self.register_tool(
            name="call_executor",
            description="Call ExecutorAgent to implement code changes for a specific step.",
            parameters={
                "type": "object",
                "properties": {
                    "step_description": {
                        "type": "string",
                        "description": "What to implement",
                    },
                    "step_id": {
                        "type": "integer",
                        "description": "Step number from the plan",
                    },
                    "context": {
                        "type": "string",
                        "description": "Additional context or previous step output",
                    },
                },
                "required": ["step_description", "step_id"],
            },
            handler=self._call_executor,
        )

        # Call Verifier
        self.register_tool(
            name="call_verifier",
            description="Call VerifierAgent to run tests, linting, and type checking.",
            parameters={
                "type": "object",
                "properties": {
                    "changed_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Files to verify",
                    },
                    "run_tests": {
                        "type": "boolean",
                        "description": "Whether to run tests",
                        "default": True,
                    },
                    "run_lint": {
                        "type": "boolean",
                        "description": "Whether to run linting",
                        "default": True,
                    },
                },
                "required": ["changed_files"],
            },
            handler=self._call_verifier,
        )

        # Call Reviewer
        self.register_tool(
            name="call_reviewer",
            description="Call ReviewerAgent to review code quality and provide feedback.",
            parameters={
                "type": "object",
                "properties": {
                    "changed_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Files to review",
                    },
                    "verification_summary": {
                        "type": "string",
                        "description": "Summary from verification phase",
                    },
                },
                "required": ["changed_files"],
            },
            handler=self._call_reviewer,
        )

        # Call UX Designer
        self.register_tool(
            name="call_ux_designer",
            description="Call UXDesignerAgent for UI/UX design, component specs, and accessibility review.",
            parameters={
                "type": "object",
                "properties": {
                    "task_type": {
                        "type": "string",
                        "enum": ["design_component", "review_ux", "create_design_system"],
                        "description": "Type of UX task",
                    },
                    "component_name": {
                        "type": "string",
                        "description": "Name of component to design (for design_component)",
                    },
                    "requirements": {
                        "type": "string",
                        "description": "Requirements or code to review",
                    },
                    "context": {
                        "type": "string",
                        "description": "Additional context for the design task",
                    },
                },
                "required": ["task_type", "requirements"],
            },
            handler=self._call_ux_designer,
        )

        # Memory tools
        self.register_tool(
            name="store_memory",
            description="Store information in memory for later use.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Memory key/identifier",
                    },
                    "value": {
                        "type": "string",
                        "description": "Information to store",
                    },
                    "memory_type": {
                        "type": "string",
                        "enum": ["short_term", "long_term"],
                        "description": "Type of memory storage",
                        "default": "short_term",
                    },
                },
                "required": ["key", "value"],
            },
            handler=self._store_memory,
        )

        self.register_tool(
            name="recall_memory",
            description="Retrieve stored information from memory.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Memory key to retrieve",
                    },
                    "memory_type": {
                        "type": "string",
                        "enum": ["short_term", "long_term"],
                        "description": "Type of memory to search",
                        "default": "short_term",
                    },
                },
                "required": ["key"],
            },
            handler=self._recall_memory,
        )

        self.register_tool(
            name="get_workflow_state",
            description="Get current workflow state and progress.",
            parameters={
                "type": "object",
                "properties": {},
            },
            handler=self._get_workflow_state,
        )

    def get_tools(self) -> list[ToolDefinition]:
        """Return orchestrator tools."""
        return self._tools

    async def _call_planner(
        self, task: str, context_files: list[str] | None = None
    ) -> str:
        """Call PlannerAgent and return result."""
        context = AgentContext(
            task_summary=task,
            relevant_files=context_files or [],
        )

        plan = await self._planner.create_plan(context, task)
        if plan:
            self._workflow_state["plan"] = plan
            return f"Plan created with {len(plan.steps)} steps:\n{plan.summary}\n\nSteps:\n" + "\n".join(
                f"  {s.id}. {s.description}" for s in plan.steps
            )
        return "Failed to create plan"

    async def _call_executor(
        self,
        step_description: str,
        step_id: int,
        context: str | None = None,
    ) -> str:
        """Call ExecutorAgent and return result."""
        agent_context = AgentContext(
            task_summary=step_description,
            previous_step_output=context,
        )

        result = await self._executor.execute_step(agent_context, step_description, step_id)
        self._workflow_state["execution_results"].append(result)

        if result.success:
            files_changed = ", ".join(fc.path for fc in result.files_changed) or "none"
            return f"Step {step_id} completed successfully.\nFiles changed: {files_changed}\nOutput: {result.output}"
        return f"Step {step_id} failed: {result.error or result.output}"

    async def _call_verifier(
        self,
        changed_files: list[str],
        run_tests: bool = True,
        run_lint: bool = True,
    ) -> str:
        """Call VerifierAgent and return result."""
        context = AgentContext(
            task_summary="Verify code changes",
            relevant_files=changed_files,
        )

        result = await self._verifier.verify_changes(context, changed_files)
        self._workflow_state["verification"] = result

        return (
            f"Verification {'passed' if result.success else 'failed'}:\n"
            f"  Tests: {result.tests_passed} passed, {result.tests_failed} failed\n"
            f"  Lint issues: {len(result.lint_issues)}\n"
            f"  Type errors: {len(result.type_errors)}\n"
            f"  Summary: {result.summary}"
        )

    async def _call_reviewer(
        self,
        changed_files: list[str],
        verification_summary: str | None = None,
    ) -> str:
        """Call ReviewerAgent and return result."""
        context = AgentContext(
            task_summary="Review code changes",
            relevant_files=changed_files,
            previous_step_output=verification_summary,
        )

        result = await self._reviewer.review_changes(context, changed_files)
        self._workflow_state["review"] = result

        status = "Approved" if result.approved else "Changes requested"
        comments = "\n".join(f"  - {c.message}" for c in result.comments) if result.comments else "  None"
        suggestions = "\n".join(f"  - {s}" for s in result.suggestions) if result.suggestions else "  None"

        return (
            f"Review {status}:\n"
            f"  Summary: {result.summary}\n"
            f"  Comments:\n{comments}\n"
            f"  Suggestions:\n{suggestions}"
        )

    async def _call_ux_designer(
        self,
        task_type: str,
        requirements: str,
        component_name: str | None = None,
        context: str | None = None,
    ) -> str:
        """Call UXDesignerAgent and return result."""
        agent_context = AgentContext(
            task_summary=f"UX Design: {task_type}",
            previous_step_output=context,
        )

        if task_type == "design_component":
            if not component_name:
                return "Error: component_name is required for design_component task"
            result = await self._ux_designer.design_component(
                agent_context, component_name, requirements
            )
            self._workflow_state["ux_design"] = result
            return (
                f"Component Design: {result.name}\n"
                f"  Description: {result.description}\n"
                f"  Accessibility: {', '.join(result.accessibility)}\n"
                f"  Interactions: {', '.join(result.interactions)}"
            )

        elif task_type == "review_ux":
            result = await self._ux_designer.review_ui(agent_context, requirements)
            self._workflow_state["ux_design"] = result
            return (
                f"UX Review Score: {result.score}/10\n"
                f"  Strengths: {', '.join(result.strengths)}\n"
                f"  Issues: {', '.join(result.issues) or 'None'}\n"
                f"  Recommendations: {', '.join(result.recommendations) or 'None'}"
            )

        elif task_type == "create_design_system":
            # Run general UX design task
            result = await self._ux_designer.run(agent_context, requirements)
            return f"Design System created:\n{result.output}"

        return f"Unknown UX task type: {task_type}"

    async def _store_memory(
        self,
        key: str,
        value: str,
        memory_type: str = "short_term",
    ) -> str:
        """Store information in memory."""
        if not self.memory:
            return "Memory system not available"

        if memory_type == "long_term":
            await self.memory.long_term.store(key, value)
        else:
            self.memory.short_term.store(key, value)

        return f"Stored '{key}' in {memory_type} memory"

    async def _recall_memory(
        self,
        key: str,
        memory_type: str = "short_term",
    ) -> str:
        """Retrieve information from memory."""
        if not self.memory:
            return "Memory system not available"

        if memory_type == "long_term":
            value = await self.memory.long_term.retrieve(key)
        else:
            value = self.memory.short_term.retrieve(key)

        if value:
            return f"Memory '{key}': {value}"
        return f"No memory found for key '{key}'"

    async def _get_workflow_state(self) -> str:
        """Get current workflow state."""
        state = self._workflow_state
        parts = ["Current workflow state:"]

        if state["plan"]:
            parts.append(f"  Plan: {len(state['plan'].steps)} steps")
        else:
            parts.append("  Plan: Not created")

        parts.append(f"  Execution results: {len(state['execution_results'])} steps completed")

        if state["verification"]:
            v = state["verification"]
            parts.append(f"  Verification: {'passed' if v.success else 'failed'}")
        else:
            parts.append("  Verification: Not run")

        if state["review"]:
            r = state["review"]
            parts.append(f"  Review: {'approved' if r.approved else 'pending changes'}")
        else:
            parts.append("  Review: Not done")

        return "\n".join(parts)

    async def process_response(
        self, response: CompletionResponse, tool_outputs: list[str]
    ) -> AgentResult:
        """Process final response into AgentResult."""
        return AgentResult(
            success=True,
            output=response.content,
            data={"workflow_state": self._workflow_state},
            tokens_used=response.input_tokens + response.output_tokens if response.input_tokens else None,
            summary_for_next_agent=response.content[:500] if response.content else "",
        )

    async def run_workflow(
        self,
        task: str,
        context_files: list[str] | None = None,
        constraints: list[str] | None = None,
    ) -> WorkflowResult:
        """Run a complete workflow orchestrated by this agent.

        The LLM decides the workflow dynamically based on the task.
        """
        # Reset workflow state
        self._workflow_state = {
            "plan": None,
            "execution_results": [],
            "verification": None,
            "review": None,
        }

        # Build context for orchestrator
        context = AgentContext(
            task_summary=task,
            relevant_files=context_files or [],
            constraints=constraints or [],
        )

        # Run the orchestrator - it will call other agents via tools
        request = f"""Complete this task by coordinating the appropriate agents:

Task: {task}

Context files: {', '.join(context_files) if context_files else 'None specified'}
Constraints: {', '.join(constraints) if constraints else 'None'}

Analyze the task and call the appropriate agents to complete it. Start with planning if needed, then execute, verify, and review."""

        result = await self.run(context, request)

        # Build WorkflowResult from workflow state
        return WorkflowResult(
            success=result.success,
            task_description=task,
            plan=self._workflow_state.get("plan"),
            execution_results=self._workflow_state.get("execution_results", []),
            verification=self._workflow_state.get("verification"),
            review=self._workflow_state.get("review"),
            pr_summary=result.output,
            total_tokens_used=result.tokens_used,
        )

    def inject_tools(
        self,
        file_tools: Any | None = None,
        code_tools: Any | None = None,
        git_tools: Any | None = None,
        sandbox: Any | None = None,
    ) -> None:
        """Inject real tool implementations into worker agents."""
        if file_tools:
            self._planner.inject_file_tools(file_tools)

        if file_tools and sandbox:
            self._executor.inject_tools(file_tools, sandbox)

        if code_tools and sandbox:
            self._verifier.inject_tools(code_tools, sandbox)

        if file_tools and git_tools:
            self._reviewer.inject_tools(file_tools, git_tools)
