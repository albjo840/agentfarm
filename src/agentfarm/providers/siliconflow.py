from __future__ import annotations

"""SiliconFlow provider - Free tier access to Qwen and other models."""

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


class SiliconFlowProvider(LLMProvider):
    """SiliconFlow provider with free tier for Qwen models.

    Available free models:
    - Qwen/Qwen2.5-7B-Instruct (fast, good for simple tasks)
    - Qwen/Qwen2.5-72B-Instruct (powerful, good for complex reasoning)
    - Qwen/Qwen2.5-Coder-7B-Instruct (specialized for code)
    - deepseek-ai/DeepSeek-V2.5 (alternative)

    Get API key at: https://cloud.siliconflow.cn/
    OpenAI-compatible API format.
    """

    BASE_URL = "https://api.siliconflow.cn/v1"

    def __init__(
        self,
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        api_key: str | None = None,
        retry_config: RetryConfig | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, retry_config=retry_config, **kwargs)
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY")
        if not self.api_key:
            raise ValueError(
                "SiliconFlow API key required. Set SILICONFLOW_API_KEY "
                "environment variable. Get key at: https://cloud.siliconflow.cn/"
            )
        self._client = httpx.AsyncClient(
            timeout=120.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    @staticmethod
    def _is_rate_limit_error(e: Exception) -> tuple[bool, float | None]:
        """Check if exception is a rate limit error (429)."""
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
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
        """Generate a completion using SiliconFlow (OpenAI-compatible)."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = [self._format_tool(t) for t in tools]
            payload["tool_choice"] = "auto"

        async def _do_request() -> CompletionResponse:
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

            return CompletionResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=choice.get("finish_reason", "stop"),
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

    def _format_tool(self, tool: ToolDefinition) -> dict[str, Any]:
        """Format tool for OpenAI-compatible format."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _parse_tool_calls(self, raw_calls: list[dict[str, Any]]) -> list[ToolCall]:
        """Parse tool calls from response."""
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

    async def __aenter__(self) -> "SiliconFlowProvider":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


# Alias for convenience
QwenProvider = SiliconFlowProvider
