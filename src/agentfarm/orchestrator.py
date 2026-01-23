from __future__ import annotations

"""Orchestrator - coordinates the PLAN→EXECUTE→VERIFY→REVIEW→SUMMARY workflow."""

import logging
from typing import Any, Callable, Awaitable

from agentfarm.agents.base import AgentContext, RecursionGuard

logger = logging.getLogger(__name__)

# Event callback type
EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
from agentfarm.agents.collaboration import AgentCollaborator, ProactiveCollaborator
from agentfarm.agents.executor import ExecutorAgent
from agentfarm.agents.planner import PlannerAgent
from agentfarm.agents.reviewer import ReviewerAgent
from agentfarm.agents.ux_designer import UXDesignerAgent
from agentfarm.agents.verifier import VerifierAgent
from agentfarm.models.schemas import (
    ExecutionResult,
    PlanStep,
    ReviewResult,
    StepStatus,
    TaskPlan,
    VerificationResult,
    WorkflowResult,
)
from agentfarm.providers.base import LLMProvider
from agentfarm.tools.file_tools import FileTools
from agentfarm.tools.code_tools import CodeTools


class Orchestrator:
    """Orchestrates multi-agent workflow for code tasks.

    Workflow: PLAN → EXECUTE → VERIFY → REVIEW → SUMMARY

    Key design for token efficiency:
    - Each agent receives minimal, focused context
    - Summaries are passed between agents, not full outputs
    - Tools are injected per-agent, not globally

    Multi-provider mode:
    - Each agent can use a different LLM provider
    - Maximizes free tier usage across providers
    - Agents collaborate with each other, not the user
    - Only orchestrator asks user questions
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        working_dir: str = ".",
        auto_inject_tools: bool = True,
        event_callback: EventCallback | None = None,
        use_multi_provider: bool = True,
        max_recursion_depth: int = 5,
        max_total_agent_calls: int = 50,
    ) -> None:
        self.working_dir = working_dir
        self._event_callback = event_callback
        self._use_multi_provider = use_multi_provider

        # Create recursion guard to prevent infinite agent loops
        # allow_self_calls=True enables parallel execution of same agent type
        self._recursion_guard = RecursionGuard(
            max_depth=max_recursion_depth,
            max_total_calls=max_total_agent_calls,
            allow_self_calls=True,  # Needed for parallel step execution
        )

        # Initialize agents with appropriate providers
        if use_multi_provider and provider is None:
            self._init_multi_provider_agents()
        else:
            # Single provider mode (legacy)
            self.provider = provider
            self.planner = PlannerAgent(provider)
            self.executor = ExecutorAgent(provider)
            self.verifier = VerifierAgent(provider)
            self.reviewer = ReviewerAgent(provider, working_dir=working_dir)
            self.ux_designer = UXDesignerAgent(provider)

        # Set recursion guard on all agents
        self.planner.set_recursion_guard(self._recursion_guard)
        self.executor.set_recursion_guard(self._recursion_guard)
        self.verifier.set_recursion_guard(self._recursion_guard)
        self.reviewer.set_recursion_guard(self._recursion_guard)
        self.ux_designer.set_recursion_guard(self._recursion_guard)

        # Track token usage across all providers
        self._total_tokens = 0

        # Agent registry for inter-agent communication
        self._agents = {
            "planner": self.planner,
            "executor": self.executor,
            "verifier": self.verifier,
            "reviewer": self.reviewer,
            "ux_designer": self.ux_designer,
        }

        # Set up collaboration system
        self._setup_collaboration()

        # Auto-inject FileTools and CodeTools if enabled
        if auto_inject_tools:
            self._auto_inject_tools()

    def _init_multi_provider_agents(self) -> None:
        """Initialize agents with different providers based on config."""
        from agentfarm.multi_provider import create_provider_for_agent, print_provider_status

        # Create providers for each agent
        planner_provider = create_provider_for_agent("planner")
        executor_provider = create_provider_for_agent("executor")
        verifier_provider = create_provider_for_agent("verifier")
        reviewer_provider = create_provider_for_agent("reviewer")
        designer_provider = create_provider_for_agent("designer")

        # Use orchestrator's provider as the main one for token tracking
        self.provider = create_provider_for_agent("orchestrator")

        # Initialize agents with their specific providers
        self.planner = PlannerAgent(planner_provider)
        self.executor = ExecutorAgent(executor_provider)
        self.verifier = VerifierAgent(verifier_provider)
        self.reviewer = ReviewerAgent(reviewer_provider, working_dir=self.working_dir)
        self.ux_designer = UXDesignerAgent(designer_provider)

        # Store providers for token tracking
        self._agent_providers = {
            "orchestrator": self.provider,
            "planner": planner_provider,
            "executor": executor_provider,
            "verifier": verifier_provider,
            "reviewer": reviewer_provider,
            "ux_designer": designer_provider,
        }

        # Print status at startup
        print_provider_status()

    def _setup_collaboration(self) -> None:
        """Set up the agent collaboration system.

        This enables agents to ask each other questions instead of asking the user.
        Only the orchestrator can ask user questions.
        """
        # Create user callback for when orchestrator needs to ask user
        async def user_callback(question: str) -> str:
            """Callback for asking user questions."""
            # In web interface, this will be handled via WebSocket
            if self._event_callback:
                await self._emit("user_question", {"question": question})
                # For now, return a placeholder - real implementation would wait for response
                return "Proceed with your best judgment."
            return "No user callback configured. Proceeding with best judgment."

        # Create collaborator with shared recursion guard
        self._collaborator = AgentCollaborator(
            user_callback=user_callback,
            recursion_guard=self._recursion_guard,
        )

        # Register all agents (this also shares the recursion guard)
        self._collaborator.register_agents(self._agents)

        # Set collaborator on all agents
        for agent in self._agents.values():
            agent.set_collaborator(self._collaborator)

        # Create ProactiveCollaborator wrapper
        self._proactive_collaborator = ProactiveCollaborator(self._collaborator)

        # Add event listener for web UI
        async def on_collaboration(collab) -> None:
            if self._event_callback:
                await self._emit("agent_collaboration", {
                    "initiator": collab.initiator,
                    "participants": collab.participants,
                    "type": collab.collaboration_type.value,
                    "topic": collab.topic,
                })

        self._proactive_collaborator.add_listener(on_collaboration)

        # Inject ProactiveCollaborator into all agents
        for agent in self._agents.values():
            agent.set_proactive_collaborator(self._proactive_collaborator)

    def get_collaboration_summary(self) -> str:
        """Get a summary of agent collaboration during the workflow."""
        if hasattr(self, '_collaborator'):
            return self._collaborator.get_collaboration_context()
        return ""

    def get_total_tokens_used(self) -> int:
        """Get total tokens used across all providers."""
        if hasattr(self, '_agent_providers'):
            return sum(p.total_tokens_used for p in self._agent_providers.values())
        return self.provider.total_tokens_used if self.provider else 0

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        """Emit an event to the callback if registered."""
        if self._event_callback:
            await self._event_callback(event, data)

    def _auto_inject_tools(self) -> None:
        """Automatically inject FileTools and CodeTools into agents that need them."""
        # Inject FileTools
        file_tools = FileTools(self.working_dir)
        self._file_tools = file_tools

        # Planner needs file tools for exploration
        self.planner.inject_file_tools(file_tools)

        # Executor needs file tools (sandbox injected separately)
        self.executor._tool_handlers["read_file"] = file_tools.read_file
        self.executor._tool_handlers["write_file"] = file_tools.write_file
        self.executor._tool_handlers["edit_file"] = file_tools.edit_file

        # Reviewer needs file tools for reading
        self.reviewer._tool_handlers["read_file"] = file_tools.read_file

        # Inject CodeTools for Verifier (CRITICAL - enables real test/lint/typecheck)
        code_tools = CodeTools(self.working_dir)
        self._code_tools = code_tools

        # Verifier needs code tools for actual verification
        self.verifier._tool_handlers["run_tests"] = code_tools.run_tests
        self.verifier._tool_handlers["run_linter"] = code_tools.run_linter
        self.verifier._tool_handlers["run_typecheck"] = code_tools.run_typecheck

    def inject_tools(
        self,
        file_tools: Any | None = None,
        code_tools: Any | None = None,
        git_tools: Any | None = None,
        sandbox: Any | None = None,
    ) -> None:
        """Inject real tool implementations into agents.

        Use this to override the auto-injected FileTools or add
        additional tools like code_tools, git_tools, and sandbox.
        """
        if file_tools:
            self._file_tools = file_tools
            self.planner.inject_file_tools(file_tools)
            # Also update executor file tools
            self.executor._tool_handlers["read_file"] = file_tools.read_file
            self.executor._tool_handlers["write_file"] = file_tools.write_file
            self.executor._tool_handlers["edit_file"] = file_tools.edit_file
            # And reviewer
            self.reviewer._tool_handlers["read_file"] = file_tools.read_file

        if file_tools and sandbox:
            self.executor.inject_tools(file_tools, sandbox)
        elif sandbox:
            # Use existing file_tools with new sandbox
            self.executor._tool_handlers["run_in_sandbox"] = sandbox.run

        if code_tools and sandbox:
            self.verifier.inject_tools(code_tools, sandbox)
        elif code_tools:
            self.verifier._tool_handlers["run_tests"] = code_tools.run_tests
            self.verifier._tool_handlers["run_linter"] = code_tools.run_linter
            self.verifier._tool_handlers["run_typecheck"] = code_tools.run_typecheck

        if file_tools and git_tools:
            self.reviewer.inject_tools(file_tools, git_tools)
        elif git_tools:
            self.reviewer._tool_handlers["get_diff"] = git_tools.get_diff

    def apply_custom_prompts(self, prompts: dict[str, str]) -> None:
        """Apply custom prompt suffixes to agents.

        Args:
            prompts: Dict mapping agent_id to custom prompt text.
                     Valid agent_ids: orchestrator, planner, executor, verifier,
                     reviewer, ux_designer (or ux)
        """
        agent_map = {
            "orchestrator": None,  # OrchestratorAgent handled separately if used
            "planner": self.planner,
            "executor": self.executor,
            "verifier": self.verifier,
            "reviewer": self.reviewer,
            "ux_designer": self.ux_designer,
            "ux": self.ux_designer,  # Alias
        }

        for agent_id, custom_text in prompts.items():
            if not custom_text or not custom_text.strip():
                continue

            agent = agent_map.get(agent_id.lower())
            if agent:
                agent.set_custom_prompt(custom_text)
                logger.debug("Applied custom prompt to %s: %s...", agent_id, custom_text[:50])

    def set_context_injector(self, injector: Any) -> None:
        """Set context injector for RAG-based context retrieval.

        The context injector allows agents to retrieve relevant context
        from uploaded files and documents during workflow execution.

        Args:
            injector: ContextInjector instance with indexed documents
        """
        self.planner.set_context_injector(injector)
        self.executor.set_context_injector(injector)
        self.verifier.set_context_injector(injector)
        self.reviewer.set_context_injector(injector)
        self.ux_designer.set_context_injector(injector)
        logger.info("Context injector set for all agents")

    async def run_workflow(
        self,
        task: str,
        context_files: list[str] | None = None,
        constraints: list[str] | None = None,
    ) -> WorkflowResult:
        """Run the complete PLAN→EXECUTE→VERIFY→REVIEW workflow.

        Args:
            task: Description of the task to accomplish
            context_files: Files relevant to the task (for focused context)
            constraints: Any constraints to follow

        Returns:
            WorkflowResult with full details of each phase
        """
        await self._emit("workflow_start", {"task": task})

        # Build initial minimal context
        context = AgentContext(
            task_summary=task,
            relevant_files=context_files or [],
            constraints=constraints or [],
        )

        execution_results: list[ExecutionResult] = []
        verification: VerificationResult | None = None
        review: ReviewResult | None = None

        # PHASE 1: PLAN
        await self._emit("stage_change", {"stage": "plan", "status": "active"})
        await self._emit("agent_message", {"agent": "planner", "content": f"Analyzing task: {task}"})
        plan = await self._run_plan_phase(context, task)
        if not plan:
            await self._emit("stage_change", {"stage": "plan", "status": "error"})
            await self._emit("agent_message", {"agent": "planner", "content": "Failed to create plan"})
            await self._emit("workflow_complete", {"success": False})
            return WorkflowResult(
                success=False,
                task_description=task,
                plan=None,
                pr_summary="Planning failed",
            )
        await self._emit("agent_message", {"agent": "planner", "content": f"Plan created: {plan.summary}"})
        await self._emit("stage_change", {"stage": "plan", "status": "complete"})
        await self._emit("tokens_update", {"tokens": self.get_total_tokens_used()})

        # PHASE 1.5: UX DESIGN (if task involves UI/frontend)
        ux_result = None
        if self._task_involves_ui(task, plan):
            await self._emit("stage_change", {"stage": "ux_design", "status": "active"})
            await self._emit("agent_message", {"agent": "ux", "content": "Analyzing UI/UX requirements..."})
            ux_result = await self._run_ux_design_phase(context, task, plan)
            if ux_result and ux_result.get("success"):
                await self._emit("agent_message", {"agent": "ux", "content": f"UI design complete: {ux_result.get('summary', 'Design ready')}"})
                await self._emit("stage_change", {"stage": "ux_design", "status": "complete"})
                # Pass UX guidance to executor via context
                context.previous_step_output = f"UX Design: {ux_result.get('summary', '')}"
            else:
                await self._emit("agent_message", {"agent": "ux", "content": "UX design phase skipped or failed"})
                await self._emit("stage_change", {"stage": "ux_design", "status": "error"})
            await self._emit("tokens_update", {"tokens": self.get_total_tokens_used()})
        else:
            # Skip UX phase - emit skipped status for UI clarity
            await self._emit("stage_change", {"stage": "ux_design", "status": "skipped"})

        # PHASE 2: EXECUTE
        await self._emit("stage_change", {"stage": "execute", "status": "active"})
        await self._emit("agent_message", {"agent": "executor", "content": f"Executing {len(plan.steps)} steps..."})
        execution_results = await self._run_execute_phase(context, plan)
        await self._emit("tokens_update", {"tokens": self.get_total_tokens_used()})

        # Check if execution failed
        failed_steps = [r for r in execution_results if not r.success]
        if failed_steps:
            await self._emit("stage_change", {"stage": "execute", "status": "error"})
            await self._emit("agent_message", {"agent": "executor", "content": f"Execution failed on {len(failed_steps)} steps"})
            await self._emit("workflow_complete", {"success": False})
            return WorkflowResult(
                success=False,
                task_description=task,
                plan=plan,
                execution_results=execution_results,
                pr_summary=f"Execution failed on steps: {[s.step_id for s in failed_steps]}",
            )
        await self._emit("agent_message", {"agent": "executor", "content": f"Executed {len(execution_results)} steps successfully"})
        await self._emit("stage_change", {"stage": "execute", "status": "complete"})

        # PHASE 3: VERIFY
        await self._emit("stage_change", {"stage": "verify", "status": "active"})
        changed_files = self._collect_changed_files(execution_results)
        await self._emit("agent_message", {"agent": "verifier", "content": f"Verifying {len(changed_files)} changed files..."})
        verification = await self._run_verify_phase(context, plan, changed_files, execution_results)
        await self._emit("tokens_update", {"tokens": self.get_total_tokens_used()})
        if verification.success:
            await self._emit("agent_message", {"agent": "verifier", "content": f"✓ {verification.tests_passed} tests passed"})
            await self._emit("stage_change", {"stage": "verify", "status": "complete"})
        else:
            await self._emit("agent_message", {"agent": "verifier", "content": f"✗ {verification.tests_failed} tests failed"})
            await self._emit("stage_change", {"stage": "verify", "status": "error"})

        # PHASE 4: REVIEW
        await self._emit("stage_change", {"stage": "review", "status": "active"})
        await self._emit("agent_message", {"agent": "reviewer", "content": "Reviewing code changes..."})
        review = await self._run_review_phase(context, plan, changed_files, verification, execution_results)
        await self._emit("tokens_update", {"tokens": self.get_total_tokens_used()})
        if review.approved:
            await self._emit("agent_message", {"agent": "reviewer", "content": "✓ Code review approved"})
            await self._emit("stage_change", {"stage": "review", "status": "complete"})
        else:
            await self._emit("agent_message", {"agent": "reviewer", "content": f"Changes requested: {len(review.suggestions)} suggestions"})
            await self._emit("stage_change", {"stage": "review", "status": "error"})

        # PHASE 5: SUMMARY
        pr_summary = self._generate_pr_summary(task, plan, execution_results, verification, review)
        success = verification.success and (review.approved if review else True)
        await self._emit("agent_message", {"agent": "orchestrator", "content": pr_summary[:200] + "..." if len(pr_summary) > 200 else pr_summary})
        await self._emit("workflow_complete", {"success": success, "tokens": self.get_total_tokens_used()})

        return WorkflowResult(
            success=success,
            task_description=task,
            plan=plan,
            execution_results=execution_results,
            verification=verification,
            review=review,
            pr_summary=pr_summary,
            total_tokens_used=self.get_total_tokens_used(),
        )

    async def _run_plan_phase(self, context: AgentContext, task: str) -> TaskPlan | None:
        """Run the planning phase."""
        return await self.planner.create_plan(context, task)

    async def _run_execute_phase(
        self, context: AgentContext, plan: TaskPlan
    ) -> list[ExecutionResult]:
        """Run the execution phase with parallel step execution.

        Uses dependency analysis to run independent steps concurrently.
        """
        from agentfarm.execution.parallel import ParallelExecutor

        # Log all steps for debugging
        logger.info("Plan has %d total steps", len(plan.steps))
        for i, s in enumerate(plan.steps):
            deps_str = f" (deps: {s.dependencies})" if s.dependencies else ""
            logger.info("  Step %d: agent=%s, desc=%s%s", i + 1, s.agent, s.description[:50], deps_str)

        executor_steps = [s for s in plan.steps if s.agent == "ExecutorAgent"]
        logger.info("Found %d ExecutorAgent steps to execute", len(executor_steps))

        if not executor_steps:
            return []

        # Create step execution function
        async def execute_step(step: PlanStep) -> ExecutionResult:
            """Execute a single step."""
            step_context = AgentContext(
                task_summary=context.task_summary,
                relevant_files=context.relevant_files,
                constraints=context.constraints,
            )
            return await self.executor.execute_step(
                step_context, step.description, step.id
            )

        # Callbacks for UI updates
        async def on_step_start(step_id: int, concurrent_ids: list[int]) -> None:
            """Emit event when step starts."""
            is_parallel = len(concurrent_ids) > 1
            await self._emit("step_start", {
                "step_id": step_id,
                "parallel": is_parallel,
                "concurrent_steps": concurrent_ids,
            })
            step = next((s for s in plan.steps if s.id == step_id), None)
            if step:
                await self._emit("agent_message", {
                    "agent": "executor",
                    "content": f"Starting step {step_id}: {step.description[:60]}..."
                })

        async def on_step_complete(step_id: int, result: ExecutionResult) -> None:
            """Emit event when step completes."""
            await self._emit("step_complete", {
                "step_id": step_id,
                "success": result.success,
                "files_changed": len(result.files_changed),
            })

        async def on_parallel_group(step_ids: list[int]) -> None:
            """Emit event when a parallel group starts."""
            await self._emit("parallel_group_start", {
                "step_ids": step_ids,
                "count": len(step_ids),
            })
            await self._emit("agent_message", {
                "agent": "executor",
                "content": f"Executing {len(step_ids)} steps in parallel: {step_ids}"
            })

        # Create parallel executor
        parallel_exec = ParallelExecutor(
            steps=plan.steps,
            execute_fn=execute_step,
            on_step_start=on_step_start,
            on_step_complete=on_step_complete,
            on_parallel_group=on_parallel_group,
            max_concurrent=4,
            stop_on_failure=False,  # Continue other parallel steps even if one fails
        )

        # Emit parallel execution start event with analysis
        summary = parallel_exec.get_execution_summary()
        await self._emit("parallel_execution_start", {
            "total_steps": len(executor_steps),
            "max_parallelism": summary["max_parallelism"],
            "parallel_groups": summary["parallel_groups"],
        })

        # Execute all steps with parallelization
        results = await parallel_exec.execute_all(agent_filter="ExecutorAgent")

        logger.info("Execute phase complete: %d results", len(results))
        return results

    async def _run_verify_phase(
        self,
        context: AgentContext,
        plan: TaskPlan,
        changed_files: list[str],
        execution_results: list[ExecutionResult] | None = None,
    ) -> VerificationResult:
        """Run the verification phase with rich context.

        Args:
            context: Base agent context
            plan: The task plan
            changed_files: Files that were modified
            execution_results: Results from execution phase (for rich context)

        Returns:
            VerificationResult with test/lint/type results
        """
        # Build rich context for verifier
        changes_summary = []
        if execution_results:
            for result in execution_results:
                if result.files_changed:
                    for fc in result.files_changed:
                        changes_summary.append(f"- {fc.path}: {fc.action}")

        context.previous_step_output = (
            f"Executed {len(plan.steps)} steps.\n"
            f"Changes made:\n" + "\n".join(changes_summary[:20]) +  # Limit for token efficiency
            f"\nFiles: {', '.join(changed_files[:10])}"  # Limit file list
        )
        context.relevant_files = changed_files

        return await self.verifier.verify_changes(context, changed_files)

    async def _run_review_phase(
        self,
        context: AgentContext,
        plan: TaskPlan,
        changed_files: list[str],
        verification: VerificationResult,
        execution_results: list[ExecutionResult] | None = None,
    ) -> ReviewResult:
        """Run the review phase with rich context.

        Args:
            context: Base agent context
            plan: The task plan
            changed_files: Files that were modified
            verification: Results from verification phase
            execution_results: Results from execution phase (for rich context)

        Returns:
            ReviewResult with approval status and comments
        """
        # Build rich context for reviewer
        verification_summary = (
            f"Verification: {verification.tests_passed} tests passed, "
            f"{verification.tests_failed} failed. "
            f"Lint issues: {len(verification.lint_issues)}. "
            f"Type errors: {len(verification.type_errors)}."
        )

        changes_summary = []
        if execution_results:
            for result in execution_results:
                if result.output:
                    changes_summary.append(f"- Step {result.step_id}: {result.output[:100]}")

        context.previous_step_output = (
            f"{verification_summary}\n"
            f"Task: {plan.summary}\n"
            f"Steps executed:\n" + "\n".join(changes_summary[:10])
        )
        context.relevant_files = changed_files

        return await self.reviewer.review_changes(context, changed_files)

    def _task_involves_ui(self, task: str, plan: TaskPlan) -> bool:
        """Check if the task involves UI/UX work."""
        task_lower = task.lower()
        plan_lower = plan.summary.lower() if plan.summary else ""

        ui_keywords = [
            "ui", "ux", "frontend", "front-end", "interface", "design",
            "component", "button", "form", "modal", "dialog", "menu",
            "layout", "style", "css", "html", "react", "vue", "svelte",
            "tailwind", "responsive", "mobile", "desktop", "visual",
            "animation", "icon", "color", "theme", "dark mode", "light mode",
            "pygame", "game", "sprite", "graphics", "render", "display",
            "window", "screen", "gui", "widget", "canvas"
        ]

        for keyword in ui_keywords:
            if keyword in task_lower or keyword in plan_lower:
                return True

        # Also check plan steps
        for step in plan.steps:
            step_lower = step.description.lower()
            for keyword in ui_keywords:
                if keyword in step_lower:
                    return True

        return False

    async def _run_ux_design_phase(
        self,
        context: AgentContext,
        task: str,
        plan: TaskPlan,
    ) -> dict[str, Any] | None:
        """Run the UX design phase for UI-related tasks.

        Supports parallel execution of multiple independent design steps.
        """
        import asyncio

        # Extract UI-related steps
        ui_steps = []
        for step in plan.steps:
            step_lower = step.description.lower()
            if any(kw in step_lower for kw in ["ui", "component", "interface", "display", "visual", "sprite", "graphics"]):
                ui_steps.append(step.description)

        # If multiple UI steps, run them in parallel
        if len(ui_steps) > 1:
            return await self._run_parallel_ux_design(context, task, ui_steps, plan)

        # Single step or general guidance
        if not ui_steps:
            design_request = f"Provide UI/UX design guidance for: {task}"
        else:
            design_request = f"Design UI components for:\n" + "\n".join(f"- {s}" for s in ui_steps)

        # Call UX designer
        ux_context = AgentContext(
            task_summary=f"UX Design: {task}",
            relevant_files=context.relevant_files,
            previous_step_output=plan.summary,
        )

        try:
            result = await self.ux_designer.run(ux_context, design_request)
            return {
                "success": result.success,
                "summary": result.summary_for_next_agent or "Design guidance provided",
                "output": result.output,
            }
        except Exception as e:
            logger.warning("UX design phase failed: %s", e)
            return None

    async def _run_parallel_ux_design(
        self,
        context: AgentContext,
        task: str,
        ui_steps: list[str],
        plan: TaskPlan,
    ) -> dict[str, Any] | None:
        """Execute multiple UX design steps in parallel."""
        import asyncio

        logger.info("Running %d UX design steps in parallel", len(ui_steps))

        # Emit parallel execution start event
        if self._event_callback:
            await self._event_callback("parallel_ux_start", {
                "total_steps": len(ui_steps),
                "steps": ui_steps,
            })

        async def design_single_component(step_description: str, step_idx: int) -> dict[str, Any]:
            """Design a single UI component."""
            ux_context = AgentContext(
                task_summary=f"UX Design: {step_description}",
                relevant_files=context.relevant_files,
                previous_step_output=plan.summary,
            )

            try:
                if self._event_callback:
                    await self._event_callback("ux_step_start", {
                        "step_idx": step_idx,
                        "description": step_description,
                    })

                result = await self.ux_designer.run(ux_context, f"Design: {step_description}")

                if self._event_callback:
                    await self._event_callback("ux_step_complete", {
                        "step_idx": step_idx,
                        "success": result.success,
                    })

                return {
                    "step": step_description,
                    "success": result.success,
                    "summary": result.summary_for_next_agent or "",
                    "output": result.output,
                }
            except Exception as e:
                logger.warning("UX design step failed: %s - %s", step_description, e)
                return {
                    "step": step_description,
                    "success": False,
                    "summary": "",
                    "output": str(e),
                }

        # Run all design steps in parallel
        tasks = [
            design_single_component(step, idx)
            for idx, step in enumerate(ui_steps)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        successful = []
        failed = []
        summaries = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed.append(ui_steps[i])
            elif result.get("success"):
                successful.append(result)
                if result.get("summary"):
                    summaries.append(result["summary"])
            else:
                failed.append(result.get("step", ui_steps[i]))

        # Emit completion event
        if self._event_callback:
            await self._event_callback("parallel_ux_complete", {
                "successful": len(successful),
                "failed": len(failed),
            })

        logger.info(
            "Parallel UX design complete: %d successful, %d failed",
            len(successful), len(failed)
        )

        # Combine summaries
        combined_summary = "\n".join(summaries) if summaries else "Design guidance provided"

        return {
            "success": len(failed) == 0,
            "summary": combined_summary,
            "output": "\n\n".join(r.get("output", "") for r in successful if isinstance(r, dict)),
            "parallel_results": {
                "successful": len(successful),
                "failed": len(failed),
                "failed_steps": failed,
            },
        }

    def _collect_changed_files(self, results: list[ExecutionResult]) -> list[str]:
        """Collect all files changed during execution."""
        files: set[str] = set()
        for result in results:
            for fc in result.files_changed:
                files.add(fc.path)
        return sorted(files)

    async def run_workflow_with_overlapping_phases(
        self,
        task: str,
        context_files: list[str] | None = None,
        constraints: list[str] | None = None,
        early_verify_threshold: float = 0.8,
    ) -> WorkflowResult:
        """Run workflow with overlapping execution and verification phases.

        This experimental mode starts verification when execution is 80% complete,
        potentially saving time on long workflows.

        Args:
            task: Description of the task
            context_files: Files relevant to the task
            constraints: Any constraints to follow
            early_verify_threshold: Start verify when this % of execute is done (0-1)

        Returns:
            WorkflowResult with full details
        """
        import asyncio

        await self._emit("workflow_start", {"task": task, "mode": "overlapping"})

        context = AgentContext(
            task_summary=task,
            relevant_files=context_files or [],
            constraints=constraints or [],
        )

        # PHASE 1: PLAN (same as normal)
        await self._emit("stage_change", {"stage": "plan", "status": "active"})
        plan = await self._run_plan_phase(context, task)
        if not plan:
            await self._emit("workflow_complete", {"success": False})
            return WorkflowResult(
                success=False,
                task_description=task,
                plan=None,
                pr_summary="Planning failed",
            )
        await self._emit("stage_change", {"stage": "plan", "status": "complete"})

        # Skip UX phase for overlapping mode (simplicity)
        await self._emit("stage_change", {"stage": "ux_design", "status": "skipped"})

        # PHASE 2+3: EXECUTE with early VERIFY
        await self._emit("stage_change", {"stage": "execute", "status": "active"})

        executor_steps = [s for s in plan.steps if s.agent == "ExecutorAgent"]
        total_steps = len(executor_steps)
        threshold_step = int(total_steps * early_verify_threshold)

        execution_results: list[ExecutionResult] = []
        early_verify_task: asyncio.Task | None = None
        early_verify_result: VerificationResult | None = None

        # Execute steps one by one, start verify when threshold reached
        for i, step in enumerate(executor_steps):
            step_context = AgentContext(
                task_summary=context.task_summary,
                relevant_files=context.relevant_files,
                constraints=context.constraints,
            )
            result = await self.executor.execute_step(step_context, step.description, step.id)
            execution_results.append(result)

            await self._emit("step_complete", {
                "step_id": step.id,
                "success": result.success,
                "progress": (i + 1) / total_steps,
            })

            # Start early verification when threshold reached
            if i + 1 >= threshold_step and early_verify_task is None:
                completed_files = self._collect_changed_files(execution_results)
                if completed_files:
                    await self._emit("agent_message", {
                        "agent": "verifier",
                        "content": f"Starting early verification ({len(completed_files)} files)..."
                    })
                    early_verify_task = asyncio.create_task(
                        self.verifier.verify_changes(context, completed_files)
                    )

        await self._emit("stage_change", {"stage": "execute", "status": "complete"})

        # Wait for early verify to complete (if started)
        changed_files = self._collect_changed_files(execution_results)
        if early_verify_task:
            await self._emit("stage_change", {"stage": "verify", "status": "active"})
            early_verify_result = await early_verify_task
            # Run full verify only on new files if early verify passed
            new_files = [f for f in changed_files if f not in set(self._collect_changed_files(execution_results[:threshold_step]))]
            if new_files and early_verify_result.success:
                await self._emit("agent_message", {
                    "agent": "verifier",
                    "content": f"Verifying {len(new_files)} additional files..."
                })
                final_verify = await self.verifier.verify_changes(context, new_files)
                # Merge results
                verification = VerificationResult(
                    success=early_verify_result.success and final_verify.success,
                    tests_passed=early_verify_result.tests_passed + final_verify.tests_passed,
                    tests_failed=early_verify_result.tests_failed + final_verify.tests_failed,
                    tests_skipped=early_verify_result.tests_skipped + final_verify.tests_skipped,
                    test_results=early_verify_result.test_results + final_verify.test_results,
                    lint_issues=early_verify_result.lint_issues + final_verify.lint_issues,
                    type_errors=early_verify_result.type_errors + final_verify.type_errors,
                    coverage_percent=final_verify.coverage_percent,
                    summary=f"Combined: {early_verify_result.summary} + {final_verify.summary}",
                )
            else:
                verification = early_verify_result
        else:
            # Normal verification
            await self._emit("stage_change", {"stage": "verify", "status": "active"})
            verification = await self._run_verify_phase(context, plan, changed_files, execution_results)

        await self._emit("stage_change", {"stage": "verify", "status": "complete" if verification.success else "error"})

        # PHASE 4: REVIEW (same as normal)
        await self._emit("stage_change", {"stage": "review", "status": "active"})
        review = await self._run_review_phase(context, plan, changed_files, verification, execution_results)
        await self._emit("stage_change", {"stage": "review", "status": "complete" if review.approved else "error"})

        # PHASE 5: SUMMARY
        pr_summary = self._generate_pr_summary(task, plan, execution_results, verification, review)
        success = verification.success and review.approved
        await self._emit("workflow_complete", {"success": success})

        return WorkflowResult(
            success=success,
            task_description=task,
            plan=plan,
            execution_results=execution_results,
            verification=verification,
            review=review,
            pr_summary=pr_summary,
            total_tokens_used=self.get_total_tokens_used(),
        )

    def _generate_pr_summary(
        self,
        task: str,
        plan: TaskPlan,
        execution_results: list[ExecutionResult],
        verification: VerificationResult | None,
        review: ReviewResult | None,
    ) -> str:
        """Generate a PR description summarizing the changes."""
        changed_files = self._collect_changed_files(execution_results)

        sections = [
            "## Summary",
            plan.summary,
            "",
            "## Changes",
        ]

        for result in execution_results:
            if result.files_changed:
                for fc in result.files_changed:
                    sections.append(f"- `{fc.path}`: {fc.action}")

        sections.extend(["", "## Verification"])
        if verification:
            sections.append(
                f"- Tests: {verification.tests_passed} passed, "
                f"{verification.tests_failed} failed"
            )
            if verification.lint_issues:
                sections.append(f"- Lint issues: {len(verification.lint_issues)}")
            if verification.coverage_percent:
                sections.append(f"- Coverage: {verification.coverage_percent:.1f}%")

        sections.extend(["", "## Review"])
        if review:
            status = "Approved" if review.approved else "Changes requested"
            sections.append(f"- Status: {status}")
            if review.suggestions:
                sections.append("- Suggestions for future:")
                for s in review.suggestions:
                    sections.append(f"  - {s}")

        return "\n".join(sections)

    async def run_single_agent(
        self,
        agent_type: str,
        task: str,
        context: AgentContext | None = None,
    ) -> Any:
        """Run a single agent for simpler tasks.

        Args:
            agent_type: "planner", "executor", "verifier", or "reviewer"
            task: Task description
            context: Optional context (will use minimal default if not provided)

        Returns:
            Agent-specific result
        """
        if context is None:
            context = AgentContext(task_summary=task)

        agents = {
            "planner": self.planner,
            "executor": self.executor,
            "verifier": self.verifier,
            "reviewer": self.reviewer,
            "ux_designer": self.ux_designer,
        }

        agent = agents.get(agent_type)
        if not agent:
            raise ValueError(f"Unknown agent type: {agent_type}")

        return await agent.run(context, task)
