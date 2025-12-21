from __future__ import annotations

"""Claude provider - Anthropic's Claude models via the Messages API."""

import json
import os
from typing import Any, AsyncIterator

import httpx

from agentfarm.providers.base import (
    CompletionResponse,
    LLMProvider,
    Message,
    RetryConfig,
    ToolCall,
    ToolDefinition,
)


class ClaudeProvider(LLMProvider):
    """Claude provider using Anthropic's Messages API.

    Supports all Claude models via the official API:
    - claude-opus-4-5-20251101 (most capable)
    - claude-sonnet-4-20250514 (balanced)
    - claude-3-5-haiku-20241022 (fast, cost-effective)

    Get API key at: https://console.anthropic.com/
    """

    BASE_URL = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        retry_config: RetryConfig | None = None,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, retry_config=retry_config, **kwargs)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter. Get key at: https://console.anthropic.com/"
            )
        self.default_max_tokens = max_tokens
        self._client = httpx.AsyncClient(
            timeout=120.0,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.API_VERSION,
                "content-type": "application/json",
            },
        )

    @staticmethod
    def _is_rate_limit_error(e: Exception) -> tuple[bool, float | None]:
        """Check if exception is a rate limit error (429)."""
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
            # Try to extract retry-after header
            retry_after = e.response.headers.get("retry-after")
            if retry_after:
                try:
                    return True, float(retry_after)
                except ValueError:
                    pass
            return True, None
        return False, None

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResponse:
        """Generate a completion using Claude with automatic retry on rate limits."""
        # Separate system message from conversation
        system_content = ""
        conversation_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                conversation_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": conversation_messages,
            "max_tokens": max_tokens or self.default_max_tokens,
            "temperature": temperature,
        }

        if system_content:
            payload["system"] = system_content

        if tools:
            payload["tools"] = [self._format_tool_for_claude(t) for t in tools]

        async def _do_request() -> CompletionResponse:
            response = await self._client.post(
                f"{self.BASE_URL}/messages",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            # Parse Claude's response format
            content_blocks = data.get("content", [])
            text_content = ""
            tool_calls: list[ToolCall] = []

            for block in content_blocks:
                if block["type"] == "text":
                    text_content += block["text"]
                elif block["type"] == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block["id"],
                            name=block["name"],
                            arguments=block.get("input", {}),
                        )
                    )

            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")

            return CompletionResponse(
                content=text_content,
                tool_calls=tool_calls,
                finish_reason=data.get("stop_reason", "end_turn"),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        result = await self._with_retry(_do_request, self._is_rate_limit_error)
        self._track_tokens(result)
        return result

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream a completion token by token."""
        # Separate system message from conversation
        system_content = ""
        conversation_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                conversation_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": conversation_messages,
            "max_tokens": max_tokens or self.default_max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        if system_content:
            payload["system"] = system_content

        async with self._client.stream(
            "POST",
            f"{self.BASE_URL}/messages",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        event_type = data.get("type")

                        if event_type == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield text
                    except json.JSONDecodeError:
                        continue

    def _format_tool_for_claude(self, tool: ToolDefinition) -> dict[str, Any]:
        """Format tool for Claude's tool use format."""
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "ClaudeProvider":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
