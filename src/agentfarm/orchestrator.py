from __future__ import annotations

"""Orchestrator - coordinates the PLAN→EXECUTE→VERIFY→REVIEW→SUMMARY workflow."""

import logging
from typing import Any, Callable, Awaitable

from agentfarm.agents.base import AgentContext, RecursionGuard

logger = logging.getLogger(__name__)

# Event callback type
EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
from agentfarm.agents.collaboration import AgentCollaborator
from agentfarm.agents.executor import ExecutorAgent
from agentfarm.agents.planner import PlannerAgent
from agentfarm.agents.reviewer import ReviewerAgent
from agentfarm.agents.verifier import VerifierAgent
from agentfarm.models.schemas import (
    ExecutionResult,
    ReviewResult,
    StepStatus,
    TaskPlan,
    VerificationResult,
    WorkflowResult,
)
from agentfarm.providers.base import LLMProvider
from agentfarm.tools.file_tools import FileTools


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
        self._recursion_guard = RecursionGuard(
            max_depth=max_recursion_depth,
            max_total_calls=max_total_agent_calls,
            allow_self_calls=False,
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
            self.reviewer = ReviewerAgent(provider)

        # Set recursion guard on all agents
        self.planner.set_recursion_guard(self._recursion_guard)
        self.executor.set_recursion_guard(self._recursion_guard)
        self.verifier.set_recursion_guard(self._recursion_guard)
        self.reviewer.set_recursion_guard(self._recursion_guard)

        # Track token usage across all providers
        self._total_tokens = 0

        # Agent registry for inter-agent communication
        self._agents = {
            "planner": self.planner,
            "executor": self.executor,
            "verifier": self.verifier,
            "reviewer": self.reviewer,
        }

        # Set up collaboration system
        self._setup_collaboration()

        # Auto-inject FileTools if enabled
        if auto_inject_tools:
            self._auto_inject_file_tools()

    def _init_multi_provider_agents(self) -> None:
        """Initialize agents with different providers based on config."""
        from agentfarm.multi_provider import create_provider_for_agent, print_provider_status

        # Create providers for each agent
        planner_provider = create_provider_for_agent("planner")
        executor_provider = create_provider_for_agent("executor")
        verifier_provider = create_provider_for_agent("verifier")
        reviewer_provider = create_provider_for_agent("reviewer")

        # Use orchestrator's provider as the main one for token tracking
        self.provider = create_provider_for_agent("orchestrator")

        # Initialize agents with their specific providers
        self.planner = PlannerAgent(planner_provider)
        self.executor = ExecutorAgent(executor_provider)
        self.verifier = VerifierAgent(verifier_provider)
        self.reviewer = ReviewerAgent(reviewer_provider)

        # Store providers for token tracking
        self._agent_providers = {
            "orchestrator": self.provider,
            "planner": planner_provider,
            "executor": executor_provider,
            "verifier": verifier_provider,
            "reviewer": reviewer_provider,
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

    def _auto_inject_file_tools(self) -> None:
        """Automatically inject FileTools into agents that need them."""
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
        verification = await self._run_verify_phase(context, plan, changed_files)
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
        review = await self._run_review_phase(context, plan, changed_files, verification)
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
        """Run the execution phase - execute all steps in order."""
        results: list[ExecutionResult] = []

        # Log all steps for debugging
        logger.info("Plan has %d total steps", len(plan.steps))
        for i, s in enumerate(plan.steps):
            logger.info("  Step %d: agent=%s, desc=%s", i + 1, s.agent, s.description[:50])

        executor_steps = [s for s in plan.steps if s.agent == "ExecutorAgent"]
        logger.info("Found %d ExecutorAgent steps to execute", len(executor_steps))

        for step in plan.steps:
            if step.agent != "ExecutorAgent":
                continue

            logger.info("Executing step %d: %s", step.id, step.description[:80])

            # Update context with previous step summary
            if results:
                context.previous_step_output = results[-1].output

            # Execute the step
            step.status = StepStatus.IN_PROGRESS
            result = await self.executor.execute_step(
                context, step.description, step.id
            )
            results.append(result)

            logger.info("Step %d result: success=%s, files_changed=%d",
                       step.id, result.success, len(result.files_changed))

            # Update step status
            step.status = StepStatus.COMPLETED if result.success else StepStatus.FAILED
            step.output = result.output

            # Stop on failure
            if not result.success:
                logger.warning("Step %d failed: %s", step.id, result.error)
                break

        logger.info("Execute phase complete: %d results", len(results))
        return results

    async def _run_verify_phase(
        self,
        context: AgentContext,
        plan: TaskPlan,
        changed_files: list[str],
    ) -> VerificationResult:
        """Run the verification phase."""
        # Update context for verifier
        context.previous_step_output = f"Executed {len(plan.steps)} steps"
        context.relevant_files = changed_files

        return await self.verifier.verify_changes(context, changed_files)

    async def _run_review_phase(
        self,
        context: AgentContext,
        plan: TaskPlan,
        changed_files: list[str],
        verification: VerificationResult,
    ) -> ReviewResult:
        """Run the review phase."""
        # Update context for reviewer
        context.previous_step_output = verification.summary
        context.relevant_files = changed_files

        return await self.reviewer.review_changes(context, changed_files)

    def _collect_changed_files(self, results: list[ExecutionResult]) -> list[str]:
        """Collect all files changed during execution."""
        files: set[str] = set()
        for result in results:
            for fc in result.files_changed:
                files.add(fc.path)
        return sorted(files)

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
        }

        agent = agents.get(agent_type)
        if not agent:
            raise ValueError(f"Unknown agent type: {agent_type}")

        return await agent.run(context, task)
