"""Tests for LLM providers."""

import pytest

from agentfarm.providers.base import (
    CompletionResponse,
    LLMProvider,
    Message,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


class TestMessage:
    def test_create_message(self):
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_system_message(self):
        msg = Message(role="system", content="You are helpful")
        assert msg.role == "system"


class TestToolCall:
    def test_create_tool_call(self):
        call = ToolCall(
            id="call_123",
            name="read_file",
            arguments={"path": "test.py"},
        )
        assert call.id == "call_123"
        assert call.name == "read_file"
        assert call.arguments["path"] == "test.py"


class TestToolResult:
    def test_successful_result(self):
        result = ToolResult(
            tool_call_id="call_123",
            output="file contents here",
        )
        assert result.output == "file contents here"
        assert result.error is None

    def test_error_result(self):
        result = ToolResult(
            tool_call_id="call_123",
            output="",
            error="File not found",
        )
        assert result.error == "File not found"


class TestCompletionResponse:
    def test_simple_response(self):
        response = CompletionResponse(
            content="Hello, how can I help?",
            input_tokens=10,
            output_tokens=5,
        )
        assert response.content == "Hello, how can I help?"
        assert response.total_tokens == 15

    def test_response_with_tools(self):
        response = CompletionResponse(
            content="Let me check that file",
            tool_calls=[
                ToolCall(id="1", name="read_file", arguments={"path": "x.py"})
            ],
        )
        assert len(response.tool_calls) == 1

    def test_total_tokens_none(self):
        response = CompletionResponse(content="test")
        assert response.total_tokens is None


class TestToolDefinition:
    def test_create_definition(self):
        tool = ToolDefinition(
            name="read_file",
            description="Read a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"],
            },
        )
        assert tool.name == "read_file"
        assert "path" in tool.parameters["properties"]


class TestLLMProviderBase:
    def test_format_tool_for_provider(self):
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object"},
        )
        formatted = LLMProvider.format_tool_for_provider(tool)

        assert formatted["type"] == "function"
        assert formatted["function"]["name"] == "test_tool"
        assert formatted["function"]["description"] == "A test tool"
