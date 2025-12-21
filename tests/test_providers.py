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
    """Test the provider auto-detection and factory function."""

    def test_explicit_provider_groq(self, monkeypatch):
        """Test explicit provider selection for Groq."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        provider = get_provider("groq")
        assert provider.model == "llama-3.3-70b-versatile"

    def test_explicit_provider_with_model(self, monkeypatch):
        """Test explicit provider with custom model."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        provider = get_provider("groq", model="mixtral-8x7b-32768")
        assert provider.model == "mixtral-8x7b-32768"

    def test_auto_detect_groq(self, monkeypatch):
        """Test auto-detection selects Groq when key is present."""
        monkeypatch.delenv("AGENTFARM_PROVIDER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        provider = get_provider()
        assert "groq" in type(provider).__module__

    def test_auto_detect_claude(self, monkeypatch):
        """Test auto-detection selects Claude when Groq not available."""
        monkeypatch.delenv("AGENTFARM_PROVIDER", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        provider = get_provider()
        assert "claude" in type(provider).__module__

    def test_auto_detect_azure(self, monkeypatch):
        """Test auto-detection selects Azure when Claude not available."""
        monkeypatch.delenv("AGENTFARM_PROVIDER", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")

        provider = get_provider()
        assert "azure" in type(provider).__module__

    def test_env_provider_override(self, monkeypatch):
        """Test AGENTFARM_PROVIDER env var overrides auto-detection."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("AGENTFARM_PROVIDER", "claude")

        provider = get_provider()
        assert "claude" in type(provider).__module__

    def test_no_provider_available(self, monkeypatch):
        """Test error when no provider can be detected."""
        monkeypatch.delenv("AGENTFARM_PROVIDER", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        with pytest.raises(ValueError, match="No LLM provider could be detected"):
            get_provider()

    def test_unknown_provider(self, monkeypatch):
        """Test error for unknown provider name."""
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("unknown_provider")
