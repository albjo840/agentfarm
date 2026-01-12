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
        """Generate a completion using Ollama.

        Uses /api/chat with full tool calling support (requires Ollama 0.13+).
        """
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
        raw_tool_calls = message.get("tool_calls", [])
        tool_calls = self._parse_tool_calls(raw_tool_calls)

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Ollama response - content length: %d, raw_tool_calls: %s", len(content), raw_tool_calls)
        if content:
            logger.info("Ollama content preview: %s", content[:500])

        # Some models output tool calls as JSON in content instead of tool_calls array
        # Check if we should parse tool calls from content
        if not tool_calls and tools and content:
            tool_calls = self._parse_tool_calls_from_content(content)
            logger.info("Parsed tool calls from content: %d calls", len(tool_calls))
            # If we found tool calls in content, clear content to avoid confusion
            if tool_calls:
                content = ""

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

    def _messages_to_prompt(self, messages: list[Message]) -> str:
        """Convert messages to a single prompt string for /api/generate."""
        parts = []
        for msg in messages:
            if msg.role == "system":
                parts.append(f"System: {msg.content}")
            elif msg.role == "user":
                parts.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                parts.append(f"Assistant: {msg.content}")
        parts.append("Assistant:")  # Prompt for response
        return "\n\n".join(parts)

    def _format_tools_as_prompt(self, tools: list[ToolDefinition]) -> str:
        """Format tools as text description for the prompt."""
        lines = ["You have access to the following tools:"]
        for tool in tools:
            lines.append(f"\n- {tool.name}: {tool.description}")
            if tool.parameters.get("properties"):
                params = ", ".join(tool.parameters["properties"].keys())
                lines.append(f"  Parameters: {params}")
        lines.append("\nTo use a tool, respond with: TOOL: tool_name(param=value)")
        return "\n".join(lines)

    def _format_tool_for_ollama(self, tool: ToolDefinition) -> dict[str, Any]:
        """Format tool for Ollama's tool calling format (for /api/chat)."""
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

    def _unescape_string_values(self, obj: Any) -> Any:
        """Recursively unescape string values in dicts/lists.

        Handles cases where LLM outputs double-escaped newlines (\\n) in JSON,
        which json.loads converts to literal \n strings instead of actual newlines.
        """
        if isinstance(obj, str):
            # Convert literal \n, \t, etc. to actual escape characters
            return obj.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
        elif isinstance(obj, dict):
            return {k: self._unescape_string_values(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._unescape_string_values(item) for item in obj]
        return obj

    def _parse_tool_calls_from_content(self, content: str) -> list[ToolCall]:
        """Parse tool calls from content field when model outputs JSON instead of using native tool_calls.

        Handles multiple formats:
        1. JSON: {"name": "write_file", "arguments": {...}}
        2. Markdown code blocks with JSON
        3. Multiple JSON objects on separate lines
        4. Python-style: write_file(path="...", content="...")
        5. Code blocks in natural language - extract and wrap in write_file
        """
        import re

        if not content:
            return []

        original_content = content
        content = content.strip()

        # Strip markdown code blocks if present (for JSON tool calls)
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        calls = []

        def validate_write_file_content(args: dict) -> dict:
            """Ensure write_file content isn't a nested JSON tool call."""
            if "content" in args:
                content_val = args["content"]
                if isinstance(content_val, str) and content_val.strip().startswith('{"name"'):
                    # Content looks like a nested tool call - try to extract actual code
                    try:
                        nested = json.loads(content_val)
                        if "arguments" in nested and "content" in nested["arguments"]:
                            # Extract the real content from nested structure
                            args["content"] = nested["arguments"]["content"]
                    except (json.JSONDecodeError, KeyError):
                        pass
            return args

        # Try to parse as single JSON object
        if content.startswith("{") and "\n{" not in content:
            try:
                data = json.loads(content)
                if "name" in data and "arguments" in data:
                    args = self._unescape_string_values(data.get("arguments", {}))
                    # Validate write_file content
                    if data["name"] == "write_file":
                        args = validate_write_file_content(args)
                    return [
                        ToolCall(
                            id="call_0",
                            name=data["name"],
                            arguments=args,
                        )
                    ]
            except json.JSONDecodeError:
                pass

        # Try to parse as JSON array
        if content.startswith("["):
            try:
                data = json.loads(content)
                for i, item in enumerate(data):
                    if "name" in item and "arguments" in item:
                        args = self._unescape_string_values(item.get("arguments", {}))
                        calls.append(
                            ToolCall(
                                id=f"call_{i}",
                                name=item["name"],
                                arguments=args,
                            )
                        )
                return calls
            except json.JSONDecodeError:
                pass

        # Handle multiple JSON objects on separate lines
        for i, line in enumerate(content.split("\n")):
            line = line.strip()
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if "name" in data and "arguments" in data:
                        args = self._unescape_string_values(data.get("arguments", {}))
                        # Validate write_file content
                        if data["name"] == "write_file":
                            args = validate_write_file_content(args)
                        calls.append(
                            ToolCall(
                                id=f"call_{i}",
                                name=data["name"],
                                arguments=args,
                            )
                        )
                except json.JSONDecodeError:
                    continue

        if calls:
            return calls

        # Try Python-style function calls: write_file(path="...", content="...")
        # Match tool_name(arg1="val1", arg2="val2")
        tool_pattern = r'(write_file|read_file|edit_file|run_in_sandbox)\s*\(\s*'
        for match in re.finditer(tool_pattern, content):
            tool_name = match.group(1)
            start_pos = match.end()

            # Find matching closing parenthesis (handle nested parens and strings)
            depth = 1
            in_string = None
            escape_next = False
            pos = start_pos

            while pos < len(content) and depth > 0:
                char = content[pos]
                if escape_next:
                    escape_next = False
                elif char == '\\':
                    escape_next = True
                elif char in '"\'':
                    if in_string is None:
                        in_string = char
                    elif in_string == char:
                        in_string = None
                elif in_string is None:
                    if char == '(':
                        depth += 1
                    elif char == ')':
                        depth -= 1
                pos += 1

            if depth == 0:
                args_str = content[start_pos:pos-1]
                # Parse key="value" pairs
                args = {}
                # Regex for key=value - check triple quotes BEFORE single/double quotes
                arg_pattern = r'(\w+)\s*=\s*(?:"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\'|"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\')'
                for arg_match in re.finditer(arg_pattern, args_str):
                    key = arg_match.group(1)
                    # Get whichever group matched
                    value = arg_match.group(2) or arg_match.group(3) or arg_match.group(4) or arg_match.group(5) or ""
                    # Unescape
                    value = value.replace('\\"', '"').replace("\\'", "'").replace('\\n', '\n')
                    args[key] = value

                if args:
                    calls.append(
                        ToolCall(
                            id=f"call_py_{len(calls)}",
                            name=tool_name,
                            arguments=args,
                        )
                    )

        if calls:
            return calls

        # Last resort: extract code blocks from natural language and create write_file calls
        # Look for patterns like "```python\n...code...\n```" with a filename hint
        code_block_pattern = r'```(\w+)?\s*\n([\s\S]*?)```'
        filename_hints = re.findall(r'(?:file|create|named?|called?)[:\s]+[`"\']?(\w+\.(?:py|js|ts|html|css|json|md))[`"\']?', original_content, re.IGNORECASE)

        code_blocks = re.findall(code_block_pattern, original_content)
        if code_blocks and not calls:
            for i, (lang, code) in enumerate(code_blocks):
                code = code.strip()
                if not code or len(code) < 10:
                    continue

                # Try to determine filename
                if i < len(filename_hints):
                    filename = filename_hints[i]
                elif lang == "python" or lang == "py":
                    filename = "main.py"
                elif lang in ("javascript", "js"):
                    filename = "main.js"
                elif lang in ("typescript", "ts"):
                    filename = "main.ts"
                elif lang == "html":
                    filename = "index.html"
                elif lang == "css":
                    filename = "style.css"
                else:
                    # Skip non-code blocks
                    continue

                calls.append(
                    ToolCall(
                        id=f"call_extracted_{i}",
                        name="write_file",
                        arguments={"path": filename, "content": code},
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
