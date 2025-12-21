from __future__ import annotations

"""Azure OpenAI provider - Enterprise-grade OpenAI via Azure."""

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


class AzureOpenAIProvider(LLMProvider):
    """Azure OpenAI provider for enterprise deployments.

    Requires Azure OpenAI resource with deployed models.
    Supports GPT-4, GPT-4 Turbo, GPT-3.5 Turbo deployments.

    Required environment variables:
    - AZURE_OPENAI_ENDPOINT: Your Azure OpenAI resource endpoint
    - AZURE_OPENAI_API_KEY: Your Azure OpenAI API key
    - AZURE_OPENAI_DEPLOYMENT: Your model deployment name (optional, can pass as model)

    Setup guide: https://learn.microsoft.com/en-us/azure/ai-services/openai/
    """

    API_VERSION = "2024-02-15-preview"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        endpoint: str | None = None,
        api_version: str | None = None,
        retry_config: RetryConfig | None = None,
        **kwargs: Any,
    ) -> None:
        # Model is the deployment name in Azure
        deployment = model or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4")
        super().__init__(deployment, retry_config=retry_config, **kwargs)

        self.api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Azure OpenAI API key required. Set AZURE_OPENAI_API_KEY environment "
                "variable or pass api_key parameter."
            )

        self.endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        if not self.endpoint:
            raise ValueError(
                "Azure OpenAI endpoint required. Set AZURE_OPENAI_ENDPOINT environment "
                "variable or pass endpoint parameter. "
                "Example: https://your-resource.openai.azure.com"
            )

        self.endpoint = self.endpoint.rstrip("/")
        self.api_version = api_version or self.API_VERSION

        self._client = httpx.AsyncClient(
            timeout=120.0,
            headers={
                "api-key": self.api_key,
                "Content-Type": "application/json",
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
        """Generate a completion using Azure OpenAI with automatic retry on rate limits."""
        payload: dict[str, Any] = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = [self._format_tool_for_azure(t) for t in tools]
            payload["tool_choice"] = "auto"

        url = (
            f"{self.endpoint}/openai/deployments/{self.model}"
            f"/chat/completions?api-version={self.api_version}"
        )

        async def _do_request() -> CompletionResponse:
            response = await self._client.post(url, json=payload)
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
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        url = (
            f"{self.endpoint}/openai/deployments/{self.model}"
            f"/chat/completions?api-version={self.api_version}"
        )

        async with self._client.stream("POST", url, json=payload) as response:
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

    def _format_tool_for_azure(self, tool: ToolDefinition) -> dict[str, Any]:
        """Format tool for Azure OpenAI's format (same as OpenAI)."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _parse_tool_calls(self, raw_calls: list[dict[str, Any]]) -> list[ToolCall]:
        """Parse Azure OpenAI tool calls into ToolCall objects."""
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

    async def __aenter__(self) -> "AzureOpenAIProvider":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
