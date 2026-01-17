"""Tests for LLM providers."""

import os
import pytest

from agentfarm.providers.base import (
    CompletionResponse,
    LLMProvider,
    Message,
    RateLimitError,
    RetryConfig,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from agentfarm.providers import get_provider


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


class TestRetryConfig:
    def test_default_config(self):
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0

    def test_custom_config(self):
        config = RetryConfig(max_retries=5, base_delay=0.5)
        assert config.max_retries == 5
        assert config.base_delay == 0.5


class TestRateLimitError:
    def test_basic_error(self):
        error = RateLimitError("Rate limit exceeded")
        assert str(error) == "Rate limit exceeded"
        assert error.retry_after is None
        assert error.attempts == 0

    def test_error_with_retry_after(self):
        error = RateLimitError("Rate limit exceeded", retry_after=30.0, attempts=3)
        assert error.retry_after == 30.0
        assert error.attempts == 3


class TestRetryLogic:
    """Test the retry mechanism in LLMProvider."""

    @pytest.fixture
    def mock_provider(self):
        """Create a concrete provider for testing retry logic."""
        from typing import AsyncIterator

        class MockProvider(LLMProvider):
            def __init__(self, retry_config: RetryConfig | None = None):
                super().__init__("mock-model", retry_config=retry_config)
                self.call_count = 0

            async def complete(self, messages, tools=None, temperature=0.7, max_tokens=None):
                return CompletionResponse(content="mock")

            async def stream(self, messages, temperature=0.7, max_tokens=None) -> AsyncIterator[str]:
                yield "mock"

        return MockProvider

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_first_try(self, mock_provider):
        provider = mock_provider()
        call_count = 0

        async def success_op():
            nonlocal call_count
            call_count += 1
            return "success"

        def not_rate_limit(e):
            return False, None

        result = await provider._with_retry(success_op, not_rate_limit)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self, mock_provider):
        provider = mock_provider(RetryConfig(max_retries=3, base_delay=0.01))
        call_count = 0

        async def fail_twice_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Rate limit")
            return "success"

        def is_rate_limit(e):
            return "Rate limit" in str(e), None

        result = await provider._with_retry(fail_twice_then_succeed, is_rate_limit)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_rate_limit_error(self, mock_provider):
        provider = mock_provider(RetryConfig(max_retries=2, base_delay=0.01))
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise Exception("Rate limit")

        def is_rate_limit(e):
            return True, None

        with pytest.raises(RateLimitError) as exc_info:
            await provider._with_retry(always_fail, is_rate_limit)

        assert exc_info.value.attempts == 3  # initial + 2 retries
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_rate_limit_error_not_retried(self, mock_provider):
        provider = mock_provider(RetryConfig(max_retries=3, base_delay=0.01))
        call_count = 0

        async def fail_with_other_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a rate limit error")

        def is_rate_limit(e):
            return False, None

        with pytest.raises(ValueError):
            await provider._with_retry(fail_with_other_error, is_rate_limit)

        assert call_count == 1  # No retries for non-rate-limit errors


class TestGetProvider:
    """Test the provider factory function - local-first with Ollama."""

    def test_default_provider_is_ollama(self, monkeypatch):
        """Test default provider is Ollama."""
        monkeypatch.delenv("AGENTFARM_PROVIDER", raising=False)
        provider = get_provider()
        assert "ollama" in type(provider).__module__

    def test_explicit_provider_ollama(self, monkeypatch):
        """Test explicit provider selection for Ollama."""
        provider = get_provider("ollama")
        assert "ollama" in type(provider).__module__
        assert provider.model == "qwen2.5-coder:7b"  # Default model

    def test_explicit_provider_with_model(self, monkeypatch):
        """Test explicit provider with custom model."""
        provider = get_provider("ollama", model="llama3.2")
        assert provider.model == "llama3.2"

    def test_env_model_override(self, monkeypatch):
        """Test AGENTFARM_MODEL env var overrides default model."""
        monkeypatch.setenv("AGENTFARM_MODEL", "qwen3:14b")
        provider = get_provider()
        assert provider.model == "qwen3:14b"

    def test_env_provider_override(self, monkeypatch):
        """Test AGENTFARM_PROVIDER env var selects provider."""
        monkeypatch.setenv("AGENTFARM_PROVIDER", "ollama")
        provider = get_provider()
        assert "ollama" in type(provider).__module__

    def test_router_provider(self, monkeypatch):
        """Test router provider selection."""
        provider = get_provider("router")
        assert "router" in type(provider).__module__

    def test_unknown_provider(self, monkeypatch):
        """Test error for unknown provider name."""
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("unknown_provider")

    def test_unknown_cloud_provider(self, monkeypatch):
        """Test that cloud providers are not supported (local-first design)."""
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("groq")
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("claude")
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("azure")
