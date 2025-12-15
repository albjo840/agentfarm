from __future__ import annotations

"""Groq provider - fast, free-tier LLM execution."""

import json
import os
from typing import Any, AsyncIterator

import httpx

from agentfarm.providers.base import (
    CompletionResponse,
    LLMProvider,
    Message,
    ToolCall,
    ToolDefinition,
)


class GroqProvider(LLMProvider):
    """Groq provider for fast, free-tier LLM execution.

    Groq offers generous free tier with models like:
    - llama-3.3-70b-versatile (recommended)
    - llama-3.1-8b-instant (faster)
    - mixtral-8x7b-32768

    Get API key at: https://console.groq.com/keys
    """

    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        api_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Groq API key required. Set GROQ_API_KEY environment variable "
                "or pass api_key parameter. Get key at: https://console.groq.com/keys"
            )
        self._client = httpx.AsyncClient(
            timeout=120.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResponse:
        """Generate a completion using Groq."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = [self._format_tool_for_groq(t) for t in tools]
            payload["tool_choice"] = "auto"

        response = await self._client.post(
            f"{self.BASE_URL}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content", "") or ""
        tool_calls = self._parse_tool_calls(message.get("tool_calls", []))

        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")

        result = CompletionResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        self._track_tokens(result)
        return result

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream a completion token by token."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with self._client.stream(
            "POST",
            f"{self.BASE_URL}/chat/completions",
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
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    def _format_tool_for_groq(self, tool: ToolDefinition) -> dict[str, Any]:
        """Format tool for Groq's OpenAI-compatible format."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _parse_tool_calls(self, raw_calls: list[dict[str, Any]]) -> list[ToolCall]:
        """Parse Groq tool calls into ToolCall objects."""
        calls = []
        for call in raw_calls:
            func = call.get("function", {})
            arguments = func.get("arguments", "{}")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            calls.append(
                ToolCall(
                    id=call.get("id", ""),
                    name=func.get("name", ""),
                    arguments=arguments,
                )
            )
        return calls

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "GroqProvider":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
