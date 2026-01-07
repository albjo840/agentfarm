from __future__ import annotations

"""Ollama provider - free, local LLM execution."""

import json
from typing import Any, AsyncIterator

import httpx

from agentfarm.providers.base import (
    CompletionResponse,
    LLMProvider,
    Message,
    ToolCall,
    ToolDefinition,
    truncate_messages,
)


class OllamaProvider(LLMProvider):
    """Ollama provider for local, free LLM execution.

    Requires Ollama to be running locally (default: http://localhost:11434).
    Recommended models: llama3.2, codellama, mistral, mixtral.
    """

    # Ollama models typically support 4k-8k context
    # llama3.2 supports 128k but we use conservative default
    DEFAULT_MAX_CONTEXT_TOKENS = 6000

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        max_context_tokens: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model,
            max_context_tokens=max_context_tokens or self.DEFAULT_MAX_CONTEXT_TOKENS,
            **kwargs,
        )
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=120.0)

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResponse:
        """Generate a completion using Ollama."""
        # Truncate messages to fit within context limit
        truncated_messages = truncate_messages(
            messages,
            max_tokens=self.max_context_tokens,
            preserve_system=True,
            preserve_recent=4,
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in truncated_messages],
            "stream": False,
            "options": {"temperature": temperature},
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        if tools:
            payload["tools"] = [self._format_tool_for_ollama(t) for t in tools]

        response = await self._client.post(
            f"{self.base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        message = data.get("message", {})
        content = message.get("content", "")
        tool_calls = self._parse_tool_calls(message.get("tool_calls", []))

        # Ollama provides token counts in some versions
        input_tokens = data.get("prompt_eval_count")
        output_tokens = data.get("eval_count")

        result = CompletionResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=data.get("done_reason", "stop"),
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
            "stream": True,
            "options": {"temperature": temperature},
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        async with self._client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content

    def _format_tool_for_ollama(self, tool: ToolDefinition) -> dict[str, Any]:
        """Format tool for Ollama's tool calling format."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _parse_tool_calls(self, raw_calls: list[dict[str, Any]]) -> list[ToolCall]:
        """Parse Ollama tool calls into ToolCall objects."""
        calls = []
        for i, call in enumerate(raw_calls):
            func = call.get("function", {})
            calls.append(
                ToolCall(
                    id=f"call_{i}",
                    name=func.get("name", ""),
                    arguments=func.get("arguments", {}),
                )
            )
        return calls

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "OllamaProvider":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
