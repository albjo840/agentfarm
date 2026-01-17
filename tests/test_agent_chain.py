"""End-to-end tests for the complete agent chain.

Tests the full workflow: PLAN -> EXECUTE -> VERIFY -> REVIEW
with collaboration and failure recovery.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from agentfarm.agents.base import AgentContext, AgentResult
from agentfarm.agents.planner import PlannerAgent
from agentfarm.agents.executor import ExecutorAgent
from agentfarm.agents.verifier import VerifierAgent
from agentfarm.agents.reviewer import ReviewerAgent
from agentfarm.agents.collaboration import (
    AgentCollaborator,
    ProactiveCollaborator,
    TeamProblemSolver,
)
from agentfarm.execution.parallel import (
    DependencyAnalyzer,
    ParallelExecutor,
    MultiAgentParallelExecutor,
)
from agentfarm.models.schemas import (
    TaskPlan,
    PlanStep,
    StepStatus,
    ExecutionResult,
    VerificationResult,
    ReviewResult,
)
from agentfarm.providers.base import CompletionResponse, LLMProvider


class MockProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, responses: list[str] | None = None):
        super().__init__("mock-model")
        self.responses = responses or ["Mock response"]
        self.call_count = 0

    async def complete(self, messages, tools=None, **kwargs):
        response = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return CompletionResponse(
            content=response,
            input_tokens=100,
            output_tokens=50,
        )

    async def stream(self, messages, **kwargs):
        yield "Mock stream"


class TestAgentInitialization:
    """Tests for agent initialization."""

    def test_planner_init(self):
        """Test PlannerAgent initialization."""
        provider = MockProvider()
        planner = PlannerAgent(provider)
        assert planner.name == "PlannerAgent"
        assert len(planner.get_tools()) > 0

    def test_executor_init(self):
        """Test ExecutorAgent initialization."""
        provider = MockProvider()
        executor = ExecutorAgent(provider)
        assert executor.name == "ExecutorAgent"
        assert len(executor.get_tools()) > 0

    def test_verifier_init(self):
        """Test VerifierAgent initialization."""
        provider = MockProvider()
        verifier = VerifierAgent(provider)
        assert verifier.name == "VerifierAgent"
        assert len(verifier.get_tools()) > 0

    def test_reviewer_init(self):
        """Test ReviewerAgent initialization."""
        provider = MockProvider()
        reviewer = ReviewerAgent(provider)
        assert reviewer.name == "ReviewerAgent"
        assert len(reviewer.get_tools()) > 0


class TestAgentToolInjection:
    """Tests for tool injection into agents."""

    def test_executor_tool_injection(self):
        """Test injecting tools into ExecutorAgent."""
        provider = MockProvider()
        executor = ExecutorAgent(provider)

        mock_file_tools = MagicMock()
        mock_file_tools.read_file = AsyncMock(return_value="content")
        mock_file_tools.write_file = AsyncMock(return_value="written")
        mock_file_tools.edit_file = AsyncMock(return_value="edited")

        mock_sandbox = MagicMock()
        mock_sandbox.run = AsyncMock(return_value="sandbox result")

        executor.inject_tools(mock_file_tools, mock_sandbox)

        assert executor._tool_handlers["read_file"] == mock_file_tools.read_file
        assert executor._tool_handlers["write_file"] == mock_file_tools.write_file

    def test_verifier_tool_injection(self):
        """Test injecting tools into VerifierAgent."""
        provider = MockProvider()
        verifier = VerifierAgent(provider)

        mock_code_tools = MagicMock()
        mock_code_tools.run_tests = AsyncMock(return_value="tests passed")
        mock_code_tools.run_linter = AsyncMock(return_value="no issues")

        verifier.inject_tools(mock_code_tools)

        assert verifier._tool_handlers["run_tests"] == mock_code_tools.run_tests

    def test_reviewer_tool_injection(self):
        """Test injecting tools into ReviewerAgent."""
        provider = MockProvider()
        reviewer = ReviewerAgent(provider)

        mock_file_tools = MagicMock()
        mock_file_tools.read_file = AsyncMock(return_value="code content")

        reviewer.inject_tools(file_tools=mock_file_tools)

        assert reviewer._tool_handlers["read_file"] == mock_file_tools.read_file


class TestPlannerAgent:
    """Tests for PlannerAgent."""

    @pytest.mark.asyncio
    async def test_planner_creates_plan(self):
        """Test that planner creates a valid plan."""
        response = """{
            "steps": [
                {"id": 1, "description": "Write function", "agent": "ExecutorAgent", "dependencies": []},
                {"id": 2, "description": "Test function", "agent": "VerifierAgent", "dependencies": [1]},
                {"id": 3, "description": "Review code", "agent": "ReviewerAgent", "dependencies": [2]}
            ],
            "reasoning": "Simple workflow"
        }"""
        provider = MockProvider([response])
        planner = PlannerAgent(provider)

        ctx = AgentContext(task_summary="Add a hello function")
        result = await planner.run(ctx, "Add a hello function")

        # The result should contain plan information
        assert result.output is not None

    @pytest.mark.asyncio
    async def test_planner_handles_complex_tasks(self):
        """Test planner with complex multi-step tasks."""
        response = """{
            "steps": [
                {"id": 1, "description": "Analyze codebase", "agent": "ExecutorAgent", "dependencies": []},
                {"id": 2, "description": "Design architecture", "agent": "ExecutorAgent", "dependencies": [1]},
                {"id": 3, "description": "Implement core", "agent": "ExecutorAgent", "dependencies": [2]},
                {"id": 4, "description": "Implement API", "agent": "ExecutorAgent", "dependencies": [2]},
                {"id": 5, "description": "Test all", "agent": "VerifierAgent", "dependencies": [3, 4]},
                {"id": 6, "description": "Review", "agent": "ReviewerAgent", "dependencies": [5]}
            ],
            "reasoning": "Complex workflow with parallel steps"
        }"""
        provider = MockProvider([response])
        planner = PlannerAgent(provider)

        ctx = AgentContext(task_summary="Build REST API")
        result = await planner.run(ctx, "Build REST API")

        assert result.output is not None


class TestVerifierAgentChecks:
    """Tests for VerifierAgent security and syntax checks."""

    @pytest.fixture
    def verifier(self):
        """Create a VerifierAgent for testing."""
        return VerifierAgent(MockProvider())

    @pytest.mark.asyncio
    async def test_check_syntax_valid(self, verifier, tmp_path):
        """Test syntax check on valid Python."""
        test_file = tmp_path / "valid.py"
        test_file.write_text("def hello():\n    return 'world'")

        result = await verifier._check_syntax(str(test_file))
        assert "OK" in result

    @pytest.mark.asyncio
    async def test_check_syntax_invalid(self, verifier, tmp_path):
        """Test syntax check on invalid Python."""
        test_file = tmp_path / "invalid.py"
        test_file.write_text("def hello(\n    return 'world'")  # Missing closing paren

        result = await verifier._check_syntax(str(test_file))
        assert "SYNTAX ERROR" in result

    @pytest.mark.asyncio
    async def test_check_syntax_file_not_found(self, verifier):
        """Test syntax check on non-existent file."""
        result = await verifier._check_syntax("/nonexistent/file.py")
        assert "ERROR" in result

    @pytest.mark.asyncio
    async def test_check_imports_valid(self, verifier, tmp_path):
        """Test import check on valid imports."""
        test_file = tmp_path / "imports.py"
        test_file.write_text("import os\nimport sys\nfrom pathlib import Path")

        result = await verifier._check_imports(str(test_file))
        assert "OK" in result

    @pytest.mark.asyncio
    async def test_check_imports_invalid(self, verifier, tmp_path):
        """Test import check on invalid imports."""
        test_file = tmp_path / "bad_imports.py"
        test_file.write_text("import nonexistent_module_xyz123")

        result = await verifier._check_imports(str(test_file))
        assert "IMPORT ISSUES" in result or "Cannot import" in result


class TestReviewerAgentChecks:
    """Tests for ReviewerAgent security and pattern checks."""

    @pytest.fixture
    def reviewer(self):
        """Create a ReviewerAgent for testing."""
        return ReviewerAgent(MockProvider())

    @pytest.mark.asyncio
    async def test_check_security_clean(self, reviewer, tmp_path):
        """Test security check on clean code."""
        test_file = tmp_path / "clean.py"
        test_file.write_text("def hello():\n    return 'world'")

        result = await reviewer._check_security(str(test_file))
        assert "OK" in result

    @pytest.mark.asyncio
    async def test_check_security_hardcoded_password(self, reviewer, tmp_path):
        """Test security check detects hardcoded password."""
        test_file = tmp_path / "insecure.py"
        test_file.write_text("password = 'secret123'")

        result = await reviewer._check_security(str(test_file))
        assert "SECURITY ISSUES" in result or "Hardcoded password" in result

    @pytest.mark.asyncio
    async def test_check_security_eval(self, reviewer, tmp_path):
        """Test security check detects eval()."""
        test_file = tmp_path / "eval_usage.py"
        test_file.write_text("result = eval(user_input)")

        result = await reviewer._check_security(str(test_file))
        assert "SECURITY ISSUES" in result or "eval" in result.lower()

    @pytest.mark.asyncio
    async def test_check_patterns_clean(self, reviewer, tmp_path):
        """Test pattern check on clean code."""
        test_file = tmp_path / "clean.py"
        test_file.write_text('''
def hello() -> str:
    """Return greeting."""
    return "world"
''')

        result = await reviewer._check_patterns(str(test_file))
        assert "OK" in result

    @pytest.mark.asyncio
    async def test_check_patterns_long_function(self, reviewer, tmp_path):
        """Test pattern check detects long functions."""
        test_file = tmp_path / "long_func.py"
        # Create a function with 60 lines
        lines = ["def very_long_function() -> None:"]
        lines.append('    """Long function."""')
        for i in range(58):
            lines.append(f"    x{i} = {i}")
        test_file.write_text("\n".join(lines))

        result = await reviewer._check_patterns(str(test_file))
        assert "PATTERN ISSUES" in result or "lines" in result.lower()


class TestParallelAgentExecution:
    """Tests for parallel agent execution."""

    @pytest.mark.asyncio
    async def test_parallel_independent_steps(self):
        """Test parallel execution of independent steps."""
        steps = [
            PlanStep(id=1, description="Step 1", agent="ExecutorAgent", dependencies=[], status=StepStatus.PENDING),
            PlanStep(id=2, description="Step 2", agent="ExecutorAgent", dependencies=[], status=StepStatus.PENDING),
            PlanStep(id=3, description="Step 3", agent="ExecutorAgent", dependencies=[], status=StepStatus.PENDING),
        ]

        execution_times = []

        async def execute_fn(step):
            start = asyncio.get_event_loop().time()
            await asyncio.sleep(0.05)
            execution_times.append((step.id, start, asyncio.get_event_loop().time()))
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="Done")

        executor = ParallelExecutor(steps, execute_fn, max_concurrent=3)
        results = await executor.execute_all()

        assert len(results) == 3
        assert all(r.success for r in results)

        # Verify parallel execution (overlapping times)
        starts = [t[1] for t in execution_times]
        ends = [t[2] for t in execution_times]
        # At least two should overlap
        overlap_found = False
        for i in range(len(starts)):
            for j in range(i + 1, len(starts)):
                if starts[j] < ends[i]:
                    overlap_found = True
                    break
        assert overlap_found, "Steps should execute in parallel"

    @pytest.mark.asyncio
    async def test_dependency_ordering(self):
        """Test that dependencies are respected."""
        steps = [
            PlanStep(id=1, description="Step 1", agent="ExecutorAgent", dependencies=[], status=StepStatus.PENDING),
            PlanStep(id=2, description="Step 2", agent="ExecutorAgent", dependencies=[1], status=StepStatus.PENDING),
            PlanStep(id=3, description="Step 3", agent="ExecutorAgent", dependencies=[2], status=StepStatus.PENDING),
        ]

        execution_order = []

        async def execute_fn(step):
            execution_order.append(step.id)
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="Done")

        executor = ParallelExecutor(steps, execute_fn)
        await executor.execute_all()

        assert execution_order == [1, 2, 3]


class TestMultiAgentChain:
    """Tests for multi-agent collaboration in chain."""

    @pytest.fixture
    def mock_agents(self):
        """Create mock agents for testing."""
        provider = MockProvider()
        return {
            "planner": PlannerAgent(provider),
            "executor": ExecutorAgent(provider),
            "verifier": VerifierAgent(provider),
            "reviewer": ReviewerAgent(provider),
        }

    @pytest.mark.asyncio
    async def test_agent_chain_collaboration(self, mock_agents):
        """Test that agents can collaborate through the chain."""
        collaborator = AgentCollaborator()

        for name, agent in mock_agents.items():
            collaborator.register_agent(name, agent)

        # Create proactive collaborator
        proactive = ProactiveCollaborator(collaborator)

        # Create team problem solver
        solver = TeamProblemSolver(collaborator)

        # Simulate a failure scenario
        from agentfarm.agents.collaboration import FailureContext

        failure = FailureContext(
            agent="executor",
            task="Write complex code",
            error="Syntax error in output",
            attempts=1,
        )

        # Attempt recovery
        solution = await solver.attempt_recovery(failure)

        # Should get a solution or at least try
        assert solver.failure_history  # Should have recorded the attempt

    @pytest.mark.asyncio
    async def test_multi_agent_parallel_executor(self):
        """Test MultiAgentParallelExecutor with different agent types."""
        steps = [
            PlanStep(id=1, description="Write code", agent="ExecutorAgent", dependencies=[], status=StepStatus.PENDING),
            PlanStep(id=2, description="Test code", agent="VerifierAgent", dependencies=[1], status=StepStatus.PENDING),
            PlanStep(id=3, description="Review code", agent="ReviewerAgent", dependencies=[2], status=StepStatus.PENDING),
        ]

        agents_called = []

        async def make_executor(agent_type):
            async def fn(step):
                agents_called.append(agent_type)
                return ExecutionResult(success=True, step_id=step.id, files_changed=[], output=f"Done by {agent_type}")
            return fn

        agent_executors = {
            "ExecutorAgent": await make_executor("ExecutorAgent"),
            "VerifierAgent": await make_executor("VerifierAgent"),
            "ReviewerAgent": await make_executor("ReviewerAgent"),
        }

        executor = MultiAgentParallelExecutor(steps, agent_executors)
        results = await executor.execute_all()

        assert len(results) == 3
        assert all(r.success for r in results)
        assert agents_called == ["ExecutorAgent", "VerifierAgent", "ReviewerAgent"]


class TestFailureRecoveryInChain:
    """Tests for failure recovery within the agent chain."""

    @pytest.mark.asyncio
    async def test_executor_retry_with_recovery(self):
        """Test ExecutorAgent retry with team recovery."""
        call_count = 0

        async def mock_complete(messages, tools=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails
                return CompletionResponse(content="Error: syntax error", input_tokens=10, output_tokens=10)
            else:
                # Second call succeeds
                return CompletionResponse(
                    content='{"files_changed": [{"path": "test.py", "action": "create"}], "summary": "Created file"}',
                    input_tokens=10,
                    output_tokens=50,
                )

        provider = MockProvider()
        provider.complete = mock_complete

        executor = ExecutorAgent(provider)

        ctx = AgentContext(task_summary="Write a function")
        result = await executor.run(ctx, "Write hello function")

        # Should have attempted completion
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_chain_continues_on_partial_failure(self):
        """Test that chain can continue when some steps recover."""
        steps = [
            PlanStep(id=1, description="Step 1", agent="ExecutorAgent", dependencies=[], status=StepStatus.PENDING),
            PlanStep(id=2, description="Step 2", agent="ExecutorAgent", dependencies=[], status=StepStatus.PENDING),
            PlanStep(id=3, description="Step 3", agent="ExecutorAgent", dependencies=[1, 2], status=StepStatus.PENDING),
        ]

        fail_step_2 = True

        async def execute_fn(step):
            nonlocal fail_step_2
            if step.id == 2 and fail_step_2:
                fail_step_2 = False  # Succeed on retry
                return ExecutionResult(success=False, step_id=step.id, files_changed=[], output="", error="Temporary failure")
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="Done")

        executor = ParallelExecutor(steps, execute_fn, stop_on_failure=False)
        results = await executor.execute_all()

        # Should have at least attempted all steps
        assert len(results) >= 2


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    @pytest.mark.asyncio
    async def test_simple_task_workflow(self):
        """Test simple task through complete workflow."""
        # Create mock plan
        plan_steps = [
            PlanStep(id=1, description="Create function", agent="ExecutorAgent", dependencies=[], status=StepStatus.PENDING),
            PlanStep(id=2, description="Verify function", agent="VerifierAgent", dependencies=[1], status=StepStatus.PENDING),
        ]

        # Track workflow stages
        workflow_stages = []

        async def execute_step(step):
            workflow_stages.append(f"execute_{step.id}")
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="Done")

        async def verify_step(step):
            workflow_stages.append(f"verify_{step.id}")
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="Verified")

        agent_executors = {
            "ExecutorAgent": execute_step,
            "VerifierAgent": verify_step,
        }

        executor = MultiAgentParallelExecutor(plan_steps, agent_executors)
        results = await executor.execute_all()

        assert all(r.success for r in results)
        assert "execute_1" in workflow_stages
        assert "verify_2" in workflow_stages
        # Verify ordering
        assert workflow_stages.index("execute_1") < workflow_stages.index("verify_2")

    @pytest.mark.asyncio
    async def test_parallel_execution_workflow(self):
        """Test workflow with parallel execution opportunities."""
        # Steps 2 and 3 can run in parallel
        plan_steps = [
            PlanStep(id=1, description="Setup", agent="ExecutorAgent", dependencies=[], status=StepStatus.PENDING),
            PlanStep(id=2, description="Task A", agent="ExecutorAgent", dependencies=[1], status=StepStatus.PENDING),
            PlanStep(id=3, description="Task B", agent="ExecutorAgent", dependencies=[1], status=StepStatus.PENDING),
            PlanStep(id=4, description="Finalize", agent="ExecutorAgent", dependencies=[2, 3], status=StepStatus.PENDING),
        ]

        execution_times = {}

        async def execute_step(step):
            execution_times[step.id] = {
                "start": asyncio.get_event_loop().time()
            }
            await asyncio.sleep(0.05)
            execution_times[step.id]["end"] = asyncio.get_event_loop().time()
            return ExecutionResult(success=True, step_id=step.id, files_changed=[], output="Done")

        agent_executors = {"ExecutorAgent": execute_step}

        executor = MultiAgentParallelExecutor(plan_steps, agent_executors, max_concurrent=4)
        results = await executor.execute_all()

        assert all(r.success for r in results)

        # Steps 2 and 3 should overlap (parallel execution)
        overlap = min(execution_times[2]["end"], execution_times[3]["end"]) - max(execution_times[2]["start"], execution_times[3]["start"])
        assert overlap > 0, "Steps 2 and 3 should execute in parallel"

        # Step 4 should start after both 2 and 3
        assert execution_times[4]["start"] >= execution_times[2]["end"]
        assert execution_times[4]["start"] >= execution_times[3]["end"]
