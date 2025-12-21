from __future__ import annotations

"""Gemini provider - Google's free-tier LLM with vision capabilities."""

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


class GeminiProvider(LLMProvider):
    """Google Gemini provider with generous free tier.

    Free tier limits (gemini-1.5-flash):
    - 15 requests per minute
    - 1 million tokens per minute
    - 1,500 requests per day

    Get API key at: https://aistudio.google.com/app/apikey
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        model: str = "gemini-1.5-flash-latest",
        api_key: str | None = None,
        retry_config: RetryConfig | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, retry_config=retry_config, **kwargs)
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API key required. Set GOOGLE_API_KEY or GEMINI_API_KEY "
                "environment variable. Get key at: https://aistudio.google.com/app/apikey"
            )
        self._client = httpx.AsyncClient(
            timeout=120.0,
            headers={"Content-Type": "application/json"},
        )

    @staticmethod
    def _is_rate_limit_error(e: Exception) -> tuple[bool, float | None]:
        """Check if exception is a rate limit error (429 or 503)."""
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code in (429, 503):
                retry_after = e.response.headers.get("retry-after")
                if retry_after:
                    try:
                        return True, float(retry_after)
                    except ValueError:
                        pass
                return True, None
        return False, None

    def _convert_messages_to_contents(self, messages: list[Message]) -> tuple[str | None, list[dict]]:
        """Convert OpenAI-style messages to Gemini contents format.

        Returns:
            Tuple of (system_instruction, contents list)
        """
        system_instruction = None
        contents = []

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}]
                })

        return system_instruction, contents

    def _convert_tools_to_gemini(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert tool definitions to Gemini format."""
        if not tools:
            return []

        function_declarations = []
        for tool in tools:
            func_decl = {
                "name": tool.name,
                "description": tool.description,
            }
            if tool.parameters:
                func_decl["parameters"] = tool.parameters
            function_declarations.append(func_decl)

        return [{"functionDeclarations": function_declarations}]

    def _parse_tool_calls(self, parts: list[dict]) -> list[ToolCall]:
        """Parse Gemini function calls into ToolCall objects."""
        calls = []
        for part in parts:
            if "functionCall" in part:
                fc = part["functionCall"]
                calls.append(
                    ToolCall(
                        id=fc.get("name", ""),
                        name=fc.get("name", ""),
                        arguments=fc.get("args", {}),
                    )
                )
        return calls

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResponse:
        """Generate a completion using Gemini."""
        system_instruction, contents = self._convert_messages_to_contents(messages)

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        if tools:
            payload["tools"] = self._convert_tools_to_gemini(tools)

        async def _do_request() -> CompletionResponse:
            url = f"{self.BASE_URL}/models/{self.model}:generateContent?key={self.api_key}"
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            # Handle empty or error responses
            if "candidates" not in data or not data["candidates"]:
                error_msg = data.get("error", {}).get("message", "No response generated")
                return CompletionResponse(
                    content=f"Error: {error_msg}",
                    tool_calls=[],
                    finish_reason="error",
                )

            candidate = data["candidates"][0]
            content_data = candidate.get("content", {})
            parts = content_data.get("parts", [])

            # Extract text content
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            content = "".join(text_parts)

            # Extract tool calls
            tool_calls = self._parse_tool_calls(parts)

            # Get usage metadata
            usage = data.get("usageMetadata", {})
            input_tokens = usage.get("promptTokenCount")
            output_tokens = usage.get("candidatesTokenCount")

            return CompletionResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=candidate.get("finishReason", "STOP"),
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
        system_instruction, contents = self._convert_messages_to_contents(messages)

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        url = f"{self.BASE_URL}/models/{self.model}:streamGenerateContent?key={self.api_key}&alt=sse"

        async with self._client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            for part in parts:
                                text = part.get("text", "")
                                if text:
                                    yield text
                    except json.JSONDecodeError:
                        continue

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "GeminiProvider":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
