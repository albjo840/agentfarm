"""Tests for the parallel execution system."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from agentfarm.execution.parallel import (
    DependencyAnalyzer,
    ParallelExecutionState,
    ParallelExecutor,
    MultiAgentParallelExecutor,
)
from agentfarm.models.schemas import PlanStep, StepStatus, ExecutionResult


class TestDependencyAnalyzer:
    """Tests for DependencyAnalyzer."""

    def _create_steps(self, step_data: list[tuple[int, list[int]]]) -> list[PlanStep]:
        """Create test steps from (id, dependencies) tuples."""
        return [
            PlanStep(
                id=step_id,
                description=f"Step {step_id}",
                dependencies=deps,
                agent="ExecutorAgent",
                status=StepStatus.PENDING,
            )
            for step_id, deps in step_data
        ]

    def test_empty_steps(self):
        """Test with no steps."""
        analyzer = DependencyAnalyzer([])
        assert analyzer.build_dependency_graph() == {}
        assert analyzer.get_parallel_groups() == []
        assert analyzer.get_max_parallelism() == 0

    def test_single_step_no_deps(self):
        """Test single step without dependencies."""
        steps = self._create_steps([(1, [])])
        analyzer = DependencyAnalyzer(steps)

        graph = analyzer.build_dependency_graph()
        assert graph == {1: []}

        groups = analyzer.get_parallel_groups()
        assert groups == [[1]]

        assert analyzer.get_max_parallelism() == 1

    def test_linear_dependencies(self):
        """Test steps with linear dependencies (1 -> 2 -> 3)."""
        steps = self._create_steps([
            (1, []),
            (2, [1]),
            (3, [2]),
        ])
        analyzer = DependencyAnalyzer(steps)

        groups = analyzer.get_parallel_groups()
        assert groups == [[1], [2], [3]]
        assert analyzer.get_max_parallelism() == 1

    def test_parallel_steps(self):
        """Test steps that can run in parallel."""
        steps = self._create_steps([
            (1, []),
            (2, []),
            (3, []),
        ])
        analyzer = DependencyAnalyzer(steps)

        groups = analyzer.get_parallel_groups()
        assert len(groups) == 1
        assert set(groups[0]) == {1, 2, 3}
        assert analyzer.get_max_parallelism() == 3

    def test_diamond_dependencies(self):
        """Test diamond dependency pattern (1 -> 2,3 -> 4)."""
        steps = self._create_steps([
            (1, []),
            (2, [1]),
            (3, [1]),
            (4, [2, 3]),
        ])
        analyzer = DependencyAnalyzer(steps)

        groups = analyzer.get_parallel_groups()
        assert len(groups) == 3
        assert groups[0] == [1]
        assert set(groups[1]) == {2, 3}
        assert groups[2] == [4]
        assert analyzer.get_max_parallelism() == 2

    def test_complex_dependencies(self):
        """Test more complex dependency graph."""
        steps = self._create_steps([
            (1, []),      # Layer 1
            (2, []),      # Layer 1
            (3, [1]),     # Layer 2
            (4, [1, 2]),  # Layer 2 (depends on both 1 and 2)
            (5, [3, 4]),  # Layer 3
        ])
        analyzer = DependencyAnalyzer(steps)

        groups = analyzer.get_parallel_groups()
        assert len(groups) == 3
        assert set(groups[0]) == {1, 2}
        assert set(groups[1]) == {3, 4}
        assert groups[2] == [5]

    def test_build_reverse_graph(self):
        """Test building reverse dependency graph (dependents)."""
        steps = self._create_steps([
            (1, []),
            (2, [1]),
            (3, [1]),
        ])
        analyzer = DependencyAnalyzer(steps)

        reverse = analyzer.build_reverse_graph()
        assert reverse == {1: [2, 3], 2: [], 3: []}

    def test_get_ready_steps_with_completed(self):
        """Test getting ready steps when some are completed."""
        steps = self._create_steps([
            (1, []),
            (2, [1]),
            (3, [1]),
            (4, [2, 3]),
        ])
        analyzer = DependencyAnalyzer(steps)

        # Initially, only step 1 is ready
        ready = analyzer.get_ready_steps(completed=set(), running=set(), failed=set())
        assert ready == [1]

        # After step 1 completes, 2 and 3 are ready
        ready = analyzer.get_ready_steps(completed={1}, running=set(), failed=set())
        assert set(ready) == {2, 3}

        # If 2 and 3 are running, nothing new is ready
        ready = analyzer.get_ready_steps(completed={1}, running={2, 3}, failed=set())
        assert ready == []

        # After 2 and 3 complete, 4 is ready
        ready = analyzer.get_ready_steps(completed={1, 2, 3}, running=set(), failed=set())
        assert ready == [4]

    def test_get_ready_steps_with_failures(self):
        """Test that failed dependencies block dependent steps."""
        steps = self._create_steps([
            (1, []),
            (2, [1]),
            (3, [2]),
        ])
        analyzer = DependencyAnalyzer(steps)

        # If step 1 failed, step 2 should not be ready
        ready = analyzer.get_ready_steps(completed=set(), running=set(), failed={1})
        assert ready == []

    def test_has_dependencies(self):
        """Test checking if a step has dependencies."""
        steps = self._create_steps([
            (1, []),
            (2, [1]),
        ])
        analyzer = DependencyAnalyzer(steps)

        assert not analyzer.has_dependencies(1)
        assert analyzer.has_dependencies(2)
        assert not analyzer.has_dependencies(99)  # Non-existent step


class TestParallelExecutionState:
    """Tests for ParallelExecutionState."""

    def test_initial_state(self):
        """Test initial state is empty."""
        state = ParallelExecutionState()
        assert state.ready == set()
        assert state.running == set()
        assert state.completed == set()
        assert state.failed == set()
        assert state.results == {}

    def test_is_done_empty(self):
        """Test is_done when no steps."""
        state = ParallelExecutionState()
        assert state.is_done

    def test_is_done_running(self):
        """Test is_done when steps running."""
        state = ParallelExecutionState()
        state.running.add(1)
        assert not state.is_done

    def test_is_done_ready(self):
        """Test is_done when steps ready."""
        state = ParallelExecutionState()
        state.ready.add(1)
        assert not state.is_done

    def test_is_done_completed(self):
        """Test is_done when all completed."""
        state = ParallelExecutionState()
        state.completed.add(1)
        assert state.is_done

    def test_get_status_summary(self):
        """Test status summary formatting."""
        state = ParallelExecutionState()
        state.ready = {1, 2}
        state.running = {3}
        state.completed = {4, 5, 6}
        state.failed = {7}

        summary = state.get_status_summary()
        assert "Ready: 2" in summary
        assert "Running: 1" in summary
        assert "Completed: 3" in summary
        assert "Failed: 1" in summary


class TestParallelExecutor:
    """Tests for ParallelExecutor."""

    def _create_steps(self, step_data: list[tuple[int, list[int], str]]) -> list[PlanStep]:
        """Create test steps from (id, dependencies, agent) tuples."""
        return [
            PlanStep(
                id=step_id,
                description=f"Step {step_id}",
                dependencies=deps,
                agent=agent,
                status=StepStatus.PENDING,
            )
            for step_id, deps, agent in step_data
        ]

    @pytest.mark.asyncio
    async def test_execute_single_step(self):
        """Test executing a single step."""
        steps = self._create_steps([(1, [], "ExecutorAgent")])

        async def execute_fn(step):
            return ExecutionResult(
                success=True,
                step_id=step.id,
                files_changed=[],
                output="Done",
            )

        executor = ParallelExecutor(steps, execute_fn)
        results = await executor.execute_all()

        assert len(results) == 1
        assert results[0].success
        assert results[0].step_id == 1

    @pytest.mark.asyncio
    async def test_execute_parallel_steps(self):
        """Test executing multiple steps in parallel."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),
            (2, [], "ExecutorAgent"),
            (3, [], "ExecutorAgent"),
        ])

        execution_order = []

        async def execute_fn(step):
            execution_order.append(step.id)
            await asyncio.sleep(0.01)  # Small delay
            return ExecutionResult(
                success=True,
                step_id=step.id,
                files_changed=[],
                output=f"Done {step.id}",
            )

        executor = ParallelExecutor(steps, execute_fn, max_concurrent=3)
        results = await executor.execute_all()

        assert len(results) == 3
        assert all(r.success for r in results)
        # All should start nearly simultaneously
        assert set(r.step_id for r in results) == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_execute_with_dependencies(self):
        """Test executing steps respecting dependencies."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),
            (2, [1], "ExecutorAgent"),
            (3, [1], "ExecutorAgent"),
            (4, [2, 3], "ExecutorAgent"),
        ])

        execution_order = []

        async def execute_fn(step):
            execution_order.append(step.id)
            return ExecutionResult(
                success=True,
                step_id=step.id,
                files_changed=[],
                output=f"Done {step.id}",
            )

        executor = ParallelExecutor(steps, execute_fn)
        results = await executor.execute_all()

        assert len(results) == 4
        # Step 1 must complete before 2 and 3
        assert execution_order.index(1) < execution_order.index(2)
        assert execution_order.index(1) < execution_order.index(3)
        # Step 4 must be after 2 and 3
        assert execution_order.index(2) < execution_order.index(4)
        assert execution_order.index(3) < execution_order.index(4)

    @pytest.mark.asyncio
    async def test_callbacks_called(self):
        """Test that callbacks are invoked."""
        steps = self._create_steps([(1, [], "ExecutorAgent")])

        step_starts = []
        step_completes = []

        async def on_step_start(step_id, concurrent_ids):
            step_starts.append(step_id)

        async def on_step_complete(step_id, result):
            step_completes.append(step_id)

        async def execute_fn(step):
            return ExecutionResult(
                success=True,
                step_id=step.id,
                files_changed=[],
                output="Done",
            )

        executor = ParallelExecutor(
            steps,
            execute_fn,
            on_step_start=on_step_start,
            on_step_complete=on_step_complete,
        )
        await executor.execute_all()

        assert step_starts == [1]
        assert step_completes == [1]

    @pytest.mark.asyncio
    async def test_stop_on_failure(self):
        """Test stopping execution on first failure."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),
            (2, [1], "ExecutorAgent"),
            (3, [2], "ExecutorAgent"),
        ])

        async def execute_fn(step):
            if step.id == 2:
                return ExecutionResult(
                    success=False,
                    step_id=step.id,
                    files_changed=[],
                    output="",
                    error="Step 2 failed",
                )
            return ExecutionResult(
                success=True,
                step_id=step.id,
                files_changed=[],
                output=f"Done {step.id}",
            )

        executor = ParallelExecutor(steps, execute_fn, stop_on_failure=True)
        results = await executor.execute_all()

        # Should have results for steps 1 and 2, but 3 should be stopped
        result_ids = {r.step_id for r in results}
        assert 1 in result_ids
        assert 2 in result_ids
        # Step 3 might be in stopped state
        assert executor.state.failed == {2}

    @pytest.mark.asyncio
    async def test_agent_filter(self):
        """Test filtering steps by agent type."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),
            (2, [], "VerifierAgent"),
            (3, [1], "ExecutorAgent"),
        ])

        executed_steps = []

        async def execute_fn(step):
            executed_steps.append(step.id)
            return ExecutionResult(
                success=True,
                step_id=step.id,
                files_changed=[],
                output=f"Done {step.id}",
            )

        executor = ParallelExecutor(steps, execute_fn)
        results = await executor.execute_all(agent_filter="ExecutorAgent")

        # Only ExecutorAgent steps should be executed
        assert set(executed_steps) == {1, 3}

    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Test handling of exceptions during execution."""
        steps = self._create_steps([(1, [], "ExecutorAgent")])

        async def execute_fn(step):
            raise ValueError("Something went wrong")

        executor = ParallelExecutor(steps, execute_fn)
        results = await executor.execute_all()

        assert len(results) == 1
        assert not results[0].success
        assert "Something went wrong" in results[0].error

    def test_get_execution_summary(self):
        """Test getting execution summary."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),
            (2, [], "ExecutorAgent"),
        ])

        async def execute_fn(step):
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="")

        executor = ParallelExecutor(steps, execute_fn)
        executor.state.completed = {1, 2}

        summary = executor.get_execution_summary()
        assert summary["total_steps"] == 2
        assert summary["completed"] == [1, 2]
        assert summary["failed"] == []


class TestMultiAgentParallelExecutor:
    """Tests for MultiAgentParallelExecutor."""

    def _create_steps(self, step_data: list[tuple[int, list[int], str]]) -> list[PlanStep]:
        """Create test steps from (id, dependencies, agent) tuples."""
        return [
            PlanStep(
                id=step_id,
                description=f"Step {step_id}",
                dependencies=deps,
                agent=agent,
                status=StepStatus.PENDING,
            )
            for step_id, deps, agent in step_data
        ]

    @pytest.mark.asyncio
    async def test_execute_multiple_agents(self):
        """Test executing steps across multiple agent types."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),
            (2, [], "VerifierAgent"),
            (3, [], "ReviewerAgent"),
        ])

        executed_by_agent = {"ExecutorAgent": [], "VerifierAgent": [], "ReviewerAgent": []}

        async def executor_fn(step):
            executed_by_agent["ExecutorAgent"].append(step.id)
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="")

        async def verifier_fn(step):
            executed_by_agent["VerifierAgent"].append(step.id)
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="")

        async def reviewer_fn(step):
            executed_by_agent["ReviewerAgent"].append(step.id)
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="")

        agent_executors = {
            "ExecutorAgent": executor_fn,
            "VerifierAgent": verifier_fn,
            "ReviewerAgent": reviewer_fn,
        }

        executor = MultiAgentParallelExecutor(steps, agent_executors)
        results = await executor.execute_all()

        assert len(results) == 3
        assert all(r.success for r in results)
        assert executed_by_agent["ExecutorAgent"] == [1]
        assert executed_by_agent["VerifierAgent"] == [2]
        assert executed_by_agent["ReviewerAgent"] == [3]

    @pytest.mark.asyncio
    async def test_mixed_agent_dependencies(self):
        """Test dependencies between different agent types."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),       # Execute code
            (2, [1], "VerifierAgent"),      # Verify after execution
            (3, [2], "ReviewerAgent"),      # Review after verification
        ])

        execution_order = []

        async def make_executor(agent_name):
            async def fn(step):
                execution_order.append((agent_name, step.id))
                return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="")
            return fn

        agent_executors = {
            "ExecutorAgent": await make_executor("ExecutorAgent"),
            "VerifierAgent": await make_executor("VerifierAgent"),
            "ReviewerAgent": await make_executor("ReviewerAgent"),
        }

        executor = MultiAgentParallelExecutor(steps, agent_executors)
        await executor.execute_all()

        # Verify execution order respects dependencies
        agents_order = [agent for agent, _ in execution_order]
        assert agents_order == ["ExecutorAgent", "VerifierAgent", "ReviewerAgent"]

    @pytest.mark.asyncio
    async def test_parallel_different_agents(self):
        """Test parallel execution of different agent types."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),
            (2, [], "VerifierAgent"),
            (3, [1, 2], "ReviewerAgent"),  # Depends on both
        ])

        start_times = {}
        end_times = {}

        async def make_executor(agent_name, delay):
            async def fn(step):
                start_times[step.id] = asyncio.get_event_loop().time()
                await asyncio.sleep(delay)
                end_times[step.id] = asyncio.get_event_loop().time()
                return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="")
            return fn

        agent_executors = {
            "ExecutorAgent": await make_executor("ExecutorAgent", 0.05),
            "VerifierAgent": await make_executor("VerifierAgent", 0.05),
            "ReviewerAgent": await make_executor("ReviewerAgent", 0.01),
        }

        executor = MultiAgentParallelExecutor(steps, agent_executors, max_concurrent=3)
        await executor.execute_all()

        # Steps 1 and 2 should overlap (run in parallel)
        overlap = min(end_times[1], end_times[2]) - max(start_times[1], start_times[2])
        assert overlap > 0, "Steps 1 and 2 should execute in parallel"

        # Step 3 should start after both 1 and 2 complete
        assert start_times[3] >= end_times[1]
        assert start_times[3] >= end_times[2]

    @pytest.mark.asyncio
    async def test_missing_agent_executor(self):
        """Test handling of missing agent executor."""
        steps = self._create_steps([(1, [], "UnknownAgent")])

        executor = MultiAgentParallelExecutor(steps, {})
        results = await executor.execute_all()

        assert len(results) == 1
        assert not results[0].success
        assert "No executor for agent: UnknownAgent" in results[0].error

    @pytest.mark.asyncio
    async def test_callbacks_with_agent_type(self):
        """Test callbacks include agent type information."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),
            (2, [], "VerifierAgent"),
        ])

        step_starts = []

        async def on_step_start(step_id, agent_type):
            step_starts.append((step_id, agent_type))

        async def execute_fn(step):
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="")

        agent_executors = {
            "ExecutorAgent": execute_fn,
            "VerifierAgent": execute_fn,
        }

        executor = MultiAgentParallelExecutor(
            steps,
            agent_executors,
            on_step_start=on_step_start,
        )
        await executor.execute_all()

        assert (1, "ExecutorAgent") in step_starts
        assert (2, "VerifierAgent") in step_starts

    def test_get_results_by_agent(self):
        """Test getting results grouped by agent type."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),
            (2, [], "ExecutorAgent"),
            (3, [], "VerifierAgent"),
        ])

        executor = MultiAgentParallelExecutor(steps, {})
        executor.state.completed = {1, 3}
        executor.state.failed = {2}

        by_agent = executor._get_results_by_agent()

        assert by_agent["ExecutorAgent"]["completed"] == 1
        assert by_agent["ExecutorAgent"]["failed"] == 1
        assert by_agent["VerifierAgent"]["completed"] == 1
        assert by_agent["VerifierAgent"]["failed"] == 0

    def test_execution_summary(self):
        """Test getting full execution summary."""
        steps = self._create_steps([
            (1, [], "ExecutorAgent"),
            (2, [], "VerifierAgent"),
        ])

        executor = MultiAgentParallelExecutor(steps, {})
        executor.state.completed = {1, 2}

        summary = executor.get_execution_summary()

        assert summary["total_steps"] == 2
        assert summary["completed"] == [1, 2]
        assert summary["failed"] == []
        assert "by_agent" in summary


class TestConcurrencyLimiting:
    """Tests for semaphore-based concurrency limiting."""

    @pytest.mark.asyncio
    async def test_max_concurrent_respected(self):
        """Test that max_concurrent limit is respected."""
        steps = [
            PlanStep(
                id=i,
                description=f"Step {i}",
                dependencies=[],
                agent="ExecutorAgent",
                status=StepStatus.PENDING,
            )
            for i in range(10)
        ]

        max_concurrent = 3
        current_running = 0
        peak_concurrent = 0

        async def execute_fn(step):
            nonlocal current_running, peak_concurrent
            current_running += 1
            peak_concurrent = max(peak_concurrent, current_running)
            await asyncio.sleep(0.01)
            current_running -= 1
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="")

        executor = ParallelExecutor(steps, execute_fn, max_concurrent=max_concurrent)
        await executor.execute_all()

        assert peak_concurrent <= max_concurrent
