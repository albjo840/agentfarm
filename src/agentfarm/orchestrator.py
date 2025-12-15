from __future__ import annotations

"""Orchestrator - coordinates the PLAN→EXECUTE→VERIFY→REVIEW→SUMMARY workflow."""

from typing import Any

from agentfarm.agents.base import AgentContext
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


class Orchestrator:
    """Orchestrates multi-agent workflow for code tasks.

    Workflow: PLAN → EXECUTE → VERIFY → REVIEW → SUMMARY

    Key design for token efficiency:
    - Each agent receives minimal, focused context
    - Summaries are passed between agents, not full outputs
    - Tools are injected per-agent, not globally
    """

    def __init__(
        self,
        provider: LLMProvider,
        working_dir: str = ".",
    ) -> None:
        self.provider = provider
        self.working_dir = working_dir

        # Initialize agents
        self.planner = PlannerAgent(provider)
        self.executor = ExecutorAgent(provider)
        self.verifier = VerifierAgent(provider)
        self.reviewer = ReviewerAgent(provider)

        # Track token usage
        self._total_tokens = 0

    def inject_tools(
        self,
        file_tools: Any | None = None,
        code_tools: Any | None = None,
        git_tools: Any | None = None,
        sandbox: Any | None = None,
    ) -> None:
        """Inject real tool implementations into agents."""
        if file_tools:
            self.planner.inject_file_tools(file_tools)

        if file_tools and sandbox:
            self.executor.inject_tools(file_tools, sandbox)

        if code_tools and sandbox:
            self.verifier.inject_tools(code_tools, sandbox)

        if file_tools and git_tools:
            self.reviewer.inject_tools(file_tools, git_tools)

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
        plan = await self._run_plan_phase(context, task)
        if not plan:
            return WorkflowResult(
                success=False,
                task_description=task,
                plan=None,
                pr_summary="Planning failed",
            )

        # PHASE 2: EXECUTE
        execution_results = await self._run_execute_phase(context, plan)

        # Check if execution failed
        failed_steps = [r for r in execution_results if not r.success]
        if failed_steps:
            return WorkflowResult(
                success=False,
                task_description=task,
                plan=plan,
                execution_results=execution_results,
                pr_summary=f"Execution failed on steps: {[s.step_id for s in failed_steps]}",
            )

        # PHASE 3: VERIFY
        changed_files = self._collect_changed_files(execution_results)
        verification = await self._run_verify_phase(context, plan, changed_files)

        # PHASE 4: REVIEW
        review = await self._run_review_phase(context, plan, changed_files, verification)

        # PHASE 5: SUMMARY
        pr_summary = self._generate_pr_summary(task, plan, execution_results, verification, review)

        return WorkflowResult(
            success=verification.success and (review.approved if review else True),
            task_description=task,
            plan=plan,
            execution_results=execution_results,
            verification=verification,
            review=review,
            pr_summary=pr_summary,
            total_tokens_used=self.provider.total_tokens_used,
        )

    async def _run_plan_phase(self, context: AgentContext, task: str) -> TaskPlan | None:
        """Run the planning phase."""
        return await self.planner.create_plan(context, task)

    async def _run_execute_phase(
        self, context: AgentContext, plan: TaskPlan
    ) -> list[ExecutionResult]:
        """Run the execution phase - execute all steps in order."""
        results: list[ExecutionResult] = []

        for step in plan.steps:
            if step.agent != "ExecutorAgent":
                continue

            # Update context with previous step summary
            if results:
                context.previous_step_output = results[-1].output

            # Execute the step
            step.status = StepStatus.IN_PROGRESS
            result = await self.executor.execute_step(
                context, step.description, step.id
            )
            results.append(result)

            # Update step status
            step.status = StepStatus.COMPLETED if result.success else StepStatus.FAILED
            step.output = result.output

            # Stop on failure
            if not result.success:
                break

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
