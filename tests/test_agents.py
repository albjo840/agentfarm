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
