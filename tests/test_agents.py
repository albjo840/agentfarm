"""Tests for agents."""

import pytest

from agentfarm.agents.base import AgentContext, AgentResult


class TestAgentContext:
    def test_minimal_context(self):
        ctx = AgentContext(task_summary="Do something")
        assert ctx.task_summary == "Do something"
        assert ctx.relevant_files == []
        assert ctx.previous_step_output is None

    def test_full_context(self):
        ctx = AgentContext(
            task_summary="Fix bug",
            relevant_files=["main.py", "utils.py"],
            previous_step_output="Found the issue",
            constraints=["No breaking changes"],
        )
        assert len(ctx.relevant_files) == 2
        assert ctx.constraints[0] == "No breaking changes"


class TestAgentResult:
    def test_successful_result(self):
        result = AgentResult(
            success=True,
            output="Done",
            data={"key": "value"},
            summary_for_next_agent="Completed task",
        )
        assert result.success
        assert result.data["key"] == "value"

    def test_failed_result(self):
        result = AgentResult(
            success=False,
            output="Error occurred",
            summary_for_next_agent="Failed to complete",
        )
        assert not result.success

    def test_with_tokens(self):
        result = AgentResult(
            success=True,
            output="Done",
            tokens_used=500,
            summary_for_next_agent="Done",
        )
        assert result.tokens_used == 500


class TestOrchestratorFileToolsInjection:
    """Test that Orchestrator auto-injects FileTools."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider for testing."""
        from typing import AsyncIterator
        from agentfarm.providers.base import CompletionResponse, LLMProvider

        class MockProvider(LLMProvider):
            async def complete(self, messages, tools=None, temperature=0.7, max_tokens=None):
                return CompletionResponse(content="mock")

            async def stream(self, messages, temperature=0.7, max_tokens=None) -> AsyncIterator[str]:
                yield "mock"

        return MockProvider("mock-model")

    def test_auto_inject_file_tools(self, mock_provider, tmp_path):
        """Test that FileTools are auto-injected when creating Orchestrator."""
        from agentfarm.orchestrator import Orchestrator

        orch = Orchestrator(mock_provider, working_dir=str(tmp_path))

        # Check that _file_tools is set
        assert hasattr(orch, "_file_tools")
        assert orch._file_tools.working_dir == tmp_path

        # Check that planner has file tools injected
        assert orch.planner._tool_handlers["read_file"] is not None
        assert orch.planner._tool_handlers["list_directory"] is not None

        # Check that executor has file tools injected
        assert orch.executor._tool_handlers["read_file"] is not None
        assert orch.executor._tool_handlers["write_file"] is not None

        # Check that reviewer has file tools injected
        assert orch.reviewer._tool_handlers["read_file"] is not None

    def test_disable_auto_inject(self, mock_provider, tmp_path):
        """Test that auto-inject can be disabled."""
        from agentfarm.orchestrator import Orchestrator

        orch = Orchestrator(mock_provider, working_dir=str(tmp_path), auto_inject_tools=False)

        # _file_tools should not be set
        assert not hasattr(orch, "_file_tools")

    @pytest.mark.asyncio
    async def test_file_tools_actually_work(self, mock_provider, tmp_path):
        """Test that injected FileTools actually work."""
        from agentfarm.orchestrator import Orchestrator

        orch = Orchestrator(mock_provider, working_dir=str(tmp_path))

        # Write a test file via the orchestrator's file tools
        result = await orch._file_tools.write_file("test.txt", "hello world")
        assert "Wrote" in result

        # Read it back
        content = await orch._file_tools.read_file("test.txt")
        assert content == "hello world"

        # Test through the planner's injected tools
        content2 = await orch.planner._tool_handlers["read_file"]("test.txt")
        assert content2 == "hello world"
