from __future__ import annotations

"""Base LLM provider abstraction for token-efficient multi-provider support."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Callable, TypeVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryConfig(BaseModel):
    """Configuration for retry behavior on rate limits."""

    max_retries: int = Field(default=3, description="Maximum number of retry attempts")
    base_delay: float = Field(default=1.0, description="Base delay in seconds")
    max_delay: float = Field(default=60.0, description="Maximum delay in seconds")
    exponential_base: float = Field(default=2.0, description="Exponential backoff base")


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


class RateLimitError(Exception):
    """Raised when rate limit is exceeded and retries are exhausted."""

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
        attempts: int = 0,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.attempts = attempts


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Implementations: OllamaProvider (free), GroqProvider (free tier),
    ClaudeProvider, AzureOpenAIProvider, AzureMLProvider.
    """

    def __init__(
        self,
        model: str,
        retry_config: RetryConfig | None = None,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.retry_config = retry_config or RetryConfig()
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

    async def _with_retry(
        self,
        operation: Callable[[], T],
        is_rate_limit_error: Callable[[Exception], tuple[bool, float | None]],
    ) -> T:
        """Execute an operation with retry logic for rate limits.

        Args:
            operation: Async callable to execute
            is_rate_limit_error: Function that checks if exception is rate limit
                                 and returns (is_rate_limit, retry_after_seconds)

        Returns:
            Result of the operation

        Raises:
            RateLimitError: If retries exhausted
            Exception: Any other error from operation
        """
        last_exception: Exception | None = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                return await operation()
            except Exception as e:
                is_rate_limit, retry_after = is_rate_limit_error(e)

                if not is_rate_limit:
                    raise

                last_exception = e

                if attempt >= self.retry_config.max_retries:
                    raise RateLimitError(
                        f"Rate limit exceeded after {attempt + 1} attempts: {e}",
                        retry_after=retry_after,
                        attempts=attempt + 1,
                    ) from e

                # Calculate delay with exponential backoff
                delay = min(
                    self.retry_config.base_delay
                    * (self.retry_config.exponential_base**attempt),
                    self.retry_config.max_delay,
                )

                # Use retry-after header if provided and larger
                if retry_after and retry_after > delay:
                    delay = min(retry_after, self.retry_config.max_delay)

                logger.warning(
                    "Rate limit hit (attempt %d/%d), retrying in %.1fs",
                    attempt + 1,
                    self.retry_config.max_retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        raise RateLimitError(
            f"Rate limit exceeded: {last_exception}",
            attempts=self.retry_config.max_retries + 1,
        )
