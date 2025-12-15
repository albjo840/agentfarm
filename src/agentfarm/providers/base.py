from __future__ import annotations

"""Base LLM provider abstraction for token-efficient multi-provider support."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator
from pydantic import BaseModel, Field


class Message(BaseModel):
    """A message in a conversation."""

    role: str = Field(..., description="user, assistant, or system")
    content: str


class ToolCall(BaseModel):
    """A tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    """Result of a tool execution."""

    tool_call_id: str
    output: str
    error: str | None = None


class CompletionResponse(BaseModel):
    """Response from an LLM completion."""

    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is not None and self.output_tokens is not None:
            return self.input_tokens + self.output_tokens
        return None


class ToolDefinition(BaseModel):
    """Definition of a tool for the LLM."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Implementations: OllamaProvider (free), GroqProvider (free tier),
    ClaudeProvider, AzureOpenAIProvider, AzureMLProvider.
    """

    def __init__(self, model: str, **kwargs: Any) -> None:
        self.model = model
        self._config = kwargs
        self._total_tokens_used = 0

    @property
    def total_tokens_used(self) -> int:
        """Total tokens used across all calls."""
        return self._total_tokens_used

    def reset_token_count(self) -> None:
        """Reset the token counter."""
        self._total_tokens_used = 0

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResponse:
        """Generate a completion.

        Args:
            messages: Conversation history
            tools: Available tools (optional)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            CompletionResponse with content and optional tool calls
        """

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream a completion token by token.

        Args:
            messages: Conversation history
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            String chunks of the response
        """

    def _track_tokens(self, response: CompletionResponse) -> None:
        """Track token usage for monitoring."""
        if response.total_tokens:
            self._total_tokens_used += response.total_tokens

    @staticmethod
    def format_tool_for_provider(tool: ToolDefinition) -> dict[str, Any]:
        """Convert ToolDefinition to provider-specific format.

        Override in subclass if provider needs different format.
        """
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
