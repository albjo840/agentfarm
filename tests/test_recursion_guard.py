"""Tests for RecursionGuard to prevent infinite agent loops."""

import pytest

from agentfarm.agents.base import RecursionGuard, RecursionLimitError


class TestRecursionGuard:
    """Tests for the RecursionGuard class."""

    def test_create_default_guard(self):
        """Test creating a guard with default settings."""
        guard = RecursionGuard()
        assert guard.max_depth == 5
        assert guard.max_total_calls == 100  # Increased from 50 for complex workflows
        assert guard.allow_self_calls is False
        assert guard.current_depth == 0
        assert guard.total_calls == 0

    def test_create_custom_guard(self):
        """Test creating a guard with custom settings."""
        guard = RecursionGuard(
            max_depth=3,
            max_total_calls=10,
            allow_self_calls=True,
        )
        assert guard.max_depth == 3
        assert guard.max_total_calls == 10
        assert guard.allow_self_calls is True

    def test_enter_and_exit(self):
        """Test basic enter and exit functionality."""
        guard = RecursionGuard()

        guard.enter("AgentA", "task1")
        assert guard.current_depth == 1
        assert guard.total_calls == 1
        assert "AgentA" in guard.call_stack

        guard.exit("AgentA")
        assert guard.current_depth == 0
        assert guard.total_calls == 1  # Total calls don't decrease

    def test_nested_calls(self):
        """Test nested agent calls."""
        guard = RecursionGuard(max_depth=5)

        guard.enter("Orchestrator", "main task")
        guard.enter("Planner", "plan task")
        guard.enter("Executor", "execute task")

        assert guard.current_depth == 3
        assert guard.call_stack == ["Orchestrator", "Planner", "Executor"]

        guard.exit("Executor")
        guard.exit("Planner")
        guard.exit("Orchestrator")

        assert guard.current_depth == 0

    def test_depth_limit_exceeded(self):
        """Test that depth limit raises RecursionLimitError."""
        guard = RecursionGuard(max_depth=2)

        guard.enter("AgentA", "task")
        guard.enter("AgentB", "task")

        with pytest.raises(RecursionLimitError) as exc_info:
            guard.enter("AgentC", "task")

        assert "Maximum recursion depth (2) exceeded" in str(exc_info.value)
        assert exc_info.value.depth == 2

    def test_cycle_detection(self):
        """Test that circular dependencies are detected."""
        guard = RecursionGuard()

        guard.enter("AgentA", "task1")
        guard.enter("AgentB", "task2")

        with pytest.raises(RecursionLimitError) as exc_info:
            guard.enter("AgentA", "task3")  # AgentA already in stack

        assert "Circular agent dependency detected" in str(exc_info.value)
        assert "AgentA" in str(exc_info.value)

    def test_cycle_detection_disabled(self):
        """Test that cycle detection can be disabled."""
        guard = RecursionGuard(allow_self_calls=True, max_depth=10)

        guard.enter("AgentA", "task1")
        guard.enter("AgentB", "task2")
        guard.enter("AgentA", "task3")  # Should not raise

        assert guard.current_depth == 3
        assert guard.call_stack.count("AgentA") == 2

    def test_total_calls_limit(self):
        """Test that total calls limit is enforced."""
        guard = RecursionGuard(max_total_calls=3)

        guard.enter("AgentA", "task1")
        guard.exit("AgentA")
        guard.enter("AgentB", "task2")
        guard.exit("AgentB")
        guard.enter("AgentC", "task3")
        guard.exit("AgentC")

        with pytest.raises(RecursionLimitError) as exc_info:
            guard.enter("AgentD", "task4")

        assert "Maximum total agent calls (3) exceeded" in str(exc_info.value)
        assert exc_info.value.total_calls == 3

    def test_repeated_identical_calls_detection(self):
        """Test detection of repeated identical calls (same agent + similar task)."""
        guard = RecursionGuard(max_total_calls=100)

        # Call same agent with same task multiple times
        # Threshold was increased from 3 to 5 to avoid false positives in multi-step workflows
        for i in range(5):
            guard.enter("AgentA", "same task")
            guard.exit("AgentA")

        # Sixth identical call should raise
        with pytest.raises(RecursionLimitError) as exc_info:
            guard.enter("AgentA", "same task")

        assert "called 5 times with identical task" in str(exc_info.value)

    def test_different_tasks_not_blocked(self):
        """Test that different tasks from same agent are not blocked."""
        guard = RecursionGuard(max_total_calls=100)

        guard.enter("AgentA", "task 1")
        guard.exit("AgentA")
        guard.enter("AgentA", "task 2")
        guard.exit("AgentA")
        guard.enter("AgentA", "task 3")
        guard.exit("AgentA")
        guard.enter("AgentA", "task 4")  # Different task, should succeed

        assert guard.total_calls == 4

    def test_get_status(self):
        """Test the status string generation."""
        guard = RecursionGuard(max_depth=5, max_total_calls=50)

        guard.enter("Orchestrator", "task")
        guard.enter("Planner", "planning")

        status = guard.get_status()
        assert "Depth: 2/5" in status
        assert "Total calls: 2/50" in status
        assert "Orchestrator → Planner" in status

    def test_is_nested(self):
        """Test the is_nested property."""
        guard = RecursionGuard()

        assert not guard.is_nested

        guard.enter("AgentA", "task")
        assert not guard.is_nested  # Only one level

        guard.enter("AgentB", "task")
        assert guard.is_nested  # Two levels

    def test_child_guard_shares_state(self):
        """Test that child guards share state with parent."""
        parent = RecursionGuard()

        parent.enter("ParentAgent", "task")

        child = parent.child_guard()
        child.enter("ChildAgent", "subtask")

        # Both should see the same state
        assert parent.current_depth == 2
        assert child.current_depth == 2
        assert parent.call_stack == child.call_stack

    def test_exception_info(self):
        """Test that RecursionLimitError contains useful info."""
        guard = RecursionGuard(max_depth=2)

        guard.enter("AgentA", "task1")
        guard.enter("AgentB", "task2")

        try:
            guard.enter("AgentC", "task3")
        except RecursionLimitError as e:
            assert e.depth == 2
            assert e.call_stack == ["AgentA", "AgentB"]
            assert e.total_calls == 2


class TestRecursionGuardIntegration:
    """Integration tests for RecursionGuard with agents."""

    @pytest.mark.asyncio
    async def test_agent_run_with_guard(self):
        """Test that BaseAgent.run() uses the recursion guard."""
        from unittest.mock import AsyncMock, MagicMock
        from agentfarm.agents.base import AgentContext, AgentResult, BaseAgent
        from agentfarm.providers.base import CompletionResponse

        # Create a mock agent
        class MockAgent(BaseAgent):
            name = "MockAgent"

            @property
            def system_prompt(self) -> str:
                return "You are a test agent."

            def get_tools(self):
                return []

            async def process_response(self, response, tool_outputs):
                return AgentResult(
                    success=True,
                    output=response.content,
                    summary_for_next_agent="Done",
                )

        # Create mock provider
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=CompletionResponse(
            content="Test response",
            tool_calls=[],
        ))

        # Test with guard that has depth 1 (will fail immediately)
        guard = RecursionGuard(max_depth=1)
        guard.enter("OtherAgent", "parent task")  # Fill up the stack

        agent = MockAgent(mock_provider)
        context = AgentContext(task_summary="test task")

        result = await agent.run(context, "test request", recursion_guard=guard)

        # Should fail due to recursion limit
        assert not result.success
        assert "recursion" in result.output.lower() or "recursion_limit" in result.data.get("error", "")

    @pytest.mark.asyncio
    async def test_agent_run_normal_case(self):
        """Test that agent runs normally with sufficient depth."""
        from unittest.mock import AsyncMock, MagicMock
        from agentfarm.agents.base import AgentContext, AgentResult, BaseAgent
        from agentfarm.providers.base import CompletionResponse

        class MockAgent(BaseAgent):
            name = "MockAgent"

            @property
            def system_prompt(self) -> str:
                return "You are a test agent."

            def get_tools(self):
                return []

            async def process_response(self, response, tool_outputs):
                return AgentResult(
                    success=True,
                    output=response.content,
                    summary_for_next_agent="Done",
                )

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=CompletionResponse(
            content="Test response",
            tool_calls=[],
        ))

        guard = RecursionGuard(max_depth=5)  # Plenty of room

        agent = MockAgent(mock_provider)
        context = AgentContext(task_summary="test task")

        result = await agent.run(context, "test request", recursion_guard=guard)

        # Should succeed
        assert result.success
        assert result.output == "Test response"
