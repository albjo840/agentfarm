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


def estimate_tokens(text: str) -> int:
    """Estimate token count for text (roughly 4 chars per token for English)."""
    return len(text) // 4 + 1


def truncate_text(text: str, max_tokens: int, keep_end: bool = False) -> str:
    """Truncate text to approximately max_tokens.

    Args:
        text: Text to truncate
        max_tokens: Maximum tokens to keep
        keep_end: If True, keep the end of the text; otherwise keep the start
    """
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text

    if keep_end:
        return "...[truncated]..." + text[-max_chars:]
    return text[:max_chars] + "...[truncated]..."


class Message(BaseModel):
    """A message in a conversation."""

    role: str = Field(..., description="user, assistant, or system")
    content: str

    def token_estimate(self) -> int:
        """Estimate tokens in this message."""
        return estimate_tokens(self.content)


def truncate_messages(
    messages: list[Message],
    max_tokens: int = 6000,
    preserve_system: bool = True,
    preserve_recent: int = 4,
) -> list[Message]:
    """Truncate message list to fit within token limit.

    Strategy:
    1. Always keep system message (if preserve_system=True)
    2. Always keep the N most recent messages (preserve_recent)
    3. Remove/truncate middle messages if needed
    4. Truncate individual long messages

    Args:
        messages: List of messages to truncate
        max_tokens: Maximum total tokens allowed
        preserve_system: Whether to always keep system message
        preserve_recent: Number of recent messages to always keep
    """
    if not messages:
        return messages

    # Separate system message and others
    system_msg = None
    other_msgs = []

    for msg in messages:
        if msg.role == "system" and preserve_system and system_msg is None:
            system_msg = msg
        else:
            other_msgs.append(msg)

    # Calculate available tokens
    system_tokens = system_msg.token_estimate() if system_msg else 0
    available_tokens = max_tokens - system_tokens

    if available_tokens <= 0:
        # System message alone exceeds limit - truncate it
        if system_msg:
            truncated_content = truncate_text(system_msg.content, max_tokens - 100)
            system_msg = Message(role="system", content=truncated_content)
        return [system_msg] if system_msg else []

    # Preserve recent messages
    recent_msgs = other_msgs[-preserve_recent:] if len(other_msgs) > preserve_recent else other_msgs
    older_msgs = other_msgs[:-preserve_recent] if len(other_msgs) > preserve_recent else []

    # Calculate tokens for recent messages
    recent_tokens = sum(msg.token_estimate() for msg in recent_msgs)

    # If recent messages exceed limit, truncate them individually
    if recent_tokens > available_tokens:
        max_per_msg = available_tokens // max(len(recent_msgs), 1)
        truncated_recent = []
        for msg in recent_msgs:
            if msg.token_estimate() > max_per_msg:
                truncated_content = truncate_text(msg.content, max_per_msg, keep_end=True)
                truncated_recent.append(Message(role=msg.role, content=truncated_content))
            else:
                truncated_recent.append(msg)
        recent_msgs = truncated_recent
        recent_tokens = sum(msg.token_estimate() for msg in recent_msgs)

    # Add older messages if space allows
    remaining_tokens = available_tokens - recent_tokens
    included_older = []

    for msg in reversed(older_msgs):  # Most recent of older first
        msg_tokens = msg.token_estimate()
        if msg_tokens <= remaining_tokens:
            included_older.insert(0, msg)
            remaining_tokens -= msg_tokens
        elif remaining_tokens > 200:  # Add truncated if enough space
            truncated_content = truncate_text(msg.content, remaining_tokens - 50)
            included_older.insert(0, Message(role=msg.role, content=truncated_content))
            break

    # Build final message list
    result = []
    if system_msg:
        result.append(system_msg)
    result.extend(included_older)
    result.extend(recent_msgs)

    return result


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

    # Default context limits per provider (can be overridden)
    DEFAULT_MAX_CONTEXT_TOKENS = 6000

    def __init__(
        self,
        model: str,
        retry_config: RetryConfig | None = None,
        max_context_tokens: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.retry_config = retry_config or RetryConfig()
        self.max_context_tokens = max_context_tokens or self.DEFAULT_MAX_CONTEXT_TOKENS
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
