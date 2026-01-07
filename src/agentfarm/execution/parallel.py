"""Parallel execution engine for AgentFarm.

Enables automatic detection and parallel execution of independent steps.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from agentfarm.models.schemas import ExecutionResult, PlanStep, TaskPlan

logger = logging.getLogger(__name__)


@dataclass
class DependencyAnalyzer:
    """Analyzes step dependencies and finds parallelizable groups.

    Uses topological sorting to identify which steps can run concurrently.
    """

    steps: list[PlanStep]

    def build_dependency_graph(self) -> dict[int, list[int]]:
        """Build a map of step ID to its dependencies."""
        return {step.id: list(step.dependencies) for step in self.steps}

    def build_reverse_graph(self) -> dict[int, list[int]]:
        """Build a map of step ID to steps that depend on it (dependents)."""
        reverse: dict[int, list[int]] = {step.id: [] for step in self.steps}
        for step in self.steps:
            for dep in step.dependencies:
                if dep in reverse:
                    reverse[dep].append(step.id)
        return reverse

    def get_ready_steps(
        self,
        completed: set[int],
        running: set[int],
        failed: set[int],
    ) -> list[int]:
        """Get steps whose dependencies are satisfied and not yet running/failed.

        A step is ready if:
        - All its dependencies are in 'completed'
        - It's not already running or completed
        - None of its dependencies failed
        """
        ready = []
        for step in self.steps:
            step_id = step.id

            # Skip if already done, running, or failed
            if step_id in completed or step_id in running or step_id in failed:
                continue

            # Skip if any dependency failed
            if any(dep in failed for dep in step.dependencies):
                continue

            # Check if all dependencies are completed
            if all(dep in completed for dep in step.dependencies):
                ready.append(step_id)

        return ready

    def get_parallel_groups(self) -> list[list[int]]:
        """Group steps into parallelizable batches (topological layers).

        Returns a list of groups, where each group contains step IDs
        that can be executed in parallel.
        """
        completed: set[int] = set()
        failed: set[int] = set()
        groups: list[list[int]] = []

        while len(completed) + len(failed) < len(self.steps):
            ready = self.get_ready_steps(completed, set(), failed)

            if not ready:
                # Remaining steps have unmet dependencies (circular or failed deps)
                remaining = [
                    s.id for s in self.steps
                    if s.id not in completed and s.id not in failed
                ]
                if remaining:
                    logger.warning(
                        "Steps with unresolvable dependencies: %s", remaining
                    )
                    groups.append(remaining)
                break

            groups.append(ready)
            completed.update(ready)

        return groups

    def get_max_parallelism(self) -> int:
        """Get the maximum number of steps that can run in parallel."""
        groups = self.get_parallel_groups()
        return max(len(group) for group in groups) if groups else 0

    def has_dependencies(self, step_id: int) -> bool:
        """Check if a step has any dependencies."""
        for step in self.steps:
            if step.id == step_id:
                return len(step.dependencies) > 0
        return False


@dataclass
class ParallelExecutionState:
    """Tracks the state of parallel step execution."""

    ready: set[int] = field(default_factory=set)
    running: set[int] = field(default_factory=set)
    completed: set[int] = field(default_factory=set)
    failed: set[int] = field(default_factory=set)
    results: dict[int, Any] = field(default_factory=dict)

    @property
    def is_done(self) -> bool:
        """Check if execution is complete (nothing running or ready)."""
        return len(self.running) == 0 and len(self.ready) == 0

    def get_status_summary(self) -> str:
        """Get a human-readable status summary."""
        return (
            f"Ready: {len(self.ready)}, Running: {len(self.running)}, "
            f"Completed: {len(self.completed)}, Failed: {len(self.failed)}"
        )


class ParallelExecutor:
    """Executes steps in parallel where dependencies allow.

    Features:
    - Automatic dependency analysis
    - Concurrent execution with semaphore limiting
    - Event callbacks for UI updates
    - Graceful failure handling
    """

    def __init__(
        self,
        steps: list[PlanStep],
        execute_fn: Callable[[PlanStep], Awaitable[ExecutionResult]],
        on_step_start: Callable[[int, list[int]], Awaitable[None]] | None = None,
        on_step_complete: Callable[[int, ExecutionResult], Awaitable[None]] | None = None,
        on_parallel_group: Callable[[list[int]], Awaitable[None]] | None = None,
        max_concurrent: int = 4,
        stop_on_failure: bool = False,
    ):
        """Initialize the parallel executor.

        Args:
            steps: List of PlanSteps to execute
            execute_fn: Async function to execute a single step
            on_step_start: Callback when a step starts (step_id, concurrent_steps)
            on_step_complete: Callback when a step completes
            on_parallel_group: Callback when a parallel group starts
            max_concurrent: Maximum concurrent executions
            stop_on_failure: If True, stop all execution on first failure
        """
        self.steps = steps
        self.execute_fn = execute_fn
        self.on_step_start = on_step_start
        self.on_step_complete = on_step_complete
        self.on_parallel_group = on_parallel_group
        self.max_concurrent = max_concurrent
        self.stop_on_failure = stop_on_failure

        self.analyzer = DependencyAnalyzer(steps)
        self.state = ParallelExecutionState()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._stop_flag = False

        # Map step ID to step for quick lookup
        self._step_map = {step.id: step for step in steps}

    async def _run_step(self, step: PlanStep, concurrent_ids: list[int]) -> ExecutionResult:
        """Run a single step with semaphore limiting."""
        from agentfarm.models.schemas import ExecutionResult, StepStatus

        if self._stop_flag:
            return ExecutionResult(
                success=False,
                step_id=step.id,
                files_changed=[],
                output="Execution stopped",
                error="Execution stopped due to previous failure",
            )

        async with self._semaphore:
            self.state.running.add(step.id)

            if self.on_step_start:
                await self.on_step_start(step.id, concurrent_ids)

            logger.info(
                "Starting step %d: %s (concurrent: %s)",
                step.id, step.description[:50], concurrent_ids
            )

            step.status = StepStatus.IN_PROGRESS

            try:
                result = await self.execute_fn(step)
            except Exception as e:
                logger.error("Step %d failed with exception: %s", step.id, e)
                result = ExecutionResult(
                    success=False,
                    step_id=step.id,
                    files_changed=[],
                    output="",
                    error=str(e),
                )

            # Update step status
            step.status = StepStatus.COMPLETED if result.success else StepStatus.FAILED
            step.output = result.output

            # Update execution state
            self.state.running.discard(step.id)
            if result.success:
                self.state.completed.add(step.id)
            else:
                self.state.failed.add(step.id)
                if self.stop_on_failure:
                    self._stop_flag = True

            self.state.results[step.id] = result

            if self.on_step_complete:
                await self.on_step_complete(step.id, result)

            logger.info(
                "Completed step %d: success=%s",
                step.id, result.success
            )

            return result

    async def execute_all(self, agent_filter: str = "ExecutorAgent") -> list[ExecutionResult]:
        """Execute all steps respecting dependencies, parallelizing where possible.

        Args:
            agent_filter: Only execute steps assigned to this agent type

        Returns:
            List of ExecutionResults for all executed steps
        """
        from agentfarm.models.schemas import ExecutionResult

        results: list[ExecutionResult] = []

        # Filter to only relevant agent steps
        relevant_step_ids = {
            step.id for step in self.steps
            if step.agent == agent_filter
        }

        # Mark non-relevant steps as "completed" for dependency resolution
        for step in self.steps:
            if step.id not in relevant_step_ids:
                self.state.completed.add(step.id)

        logger.info(
            "Starting parallel execution: %d steps for %s",
            len(relevant_step_ids), agent_filter
        )

        # Preview parallel groups
        groups = self.analyzer.get_parallel_groups()
        logger.info("Parallel groups: %s", groups)

        while not self._stop_flag:
            # Find steps ready to run
            ready_ids = self.analyzer.get_ready_steps(
                self.state.completed,
                self.state.running,
                self.state.failed,
            )

            # Filter to only relevant agent steps
            ready_ids = [sid for sid in ready_ids if sid in relevant_step_ids]

            if not ready_ids and not self.state.running:
                # No more work to do
                break

            if not ready_ids:
                # Steps are running, wait for them
                await asyncio.sleep(0.1)
                continue

            # Notify about parallel group
            if self.on_parallel_group and len(ready_ids) > 1:
                await self.on_parallel_group(ready_ids)

            logger.info("Executing parallel group: %s", ready_ids)

            # Run ready steps in parallel
            ready_steps = [self._step_map[sid] for sid in ready_ids]
            tasks = [
                self._run_step(step, ready_ids)
                for step in ready_steps
            ]

            step_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect results
            for step, result in zip(ready_steps, step_results):
                if isinstance(result, Exception):
                    error_result = ExecutionResult(
                        success=False,
                        step_id=step.id,
                        files_changed=[],
                        output="",
                        error=str(result),
                    )
                    results.append(error_result)
                    self.state.failed.add(step.id)
                else:
                    results.append(result)

        logger.info(
            "Parallel execution complete: %s",
            self.state.get_status_summary()
        )

        return results

    def get_execution_summary(self) -> dict[str, Any]:
        """Get a summary of the execution state."""
        return {
            "total_steps": len(self.steps),
            "completed": list(self.state.completed),
            "failed": list(self.state.failed),
            "max_parallelism": self.analyzer.get_max_parallelism(),
            "parallel_groups": self.analyzer.get_parallel_groups(),
        }
