"""MCP tool handlers for AgentFarm testing and introspection."""

from __future__ import annotations

from .schemas import AgentTestResult, EvalRunResult, PromptInfo

__all__ = [
    "EvalRunResult",
    "PromptInfo",
    "AgentTestResult",
]

# Lazy imports to avoid circular dependencies
def get_eval_tool_handler():
    """Get EvalToolHandler class."""
    from .eval_tools import EvalToolHandler
    return EvalToolHandler


def get_prompt_tool_handler():
    """Get PromptToolHandler class."""
    from .prompt_tools import PromptToolHandler
    return PromptToolHandler


def get_testing_tool_handler():
    """Get TestingToolHandler class."""
    from .testing_tools import TestingToolHandler
    return TestingToolHandler
