from __future__ import annotations

"""Base agent class with token-efficient context management."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from agentfarm.providers.base import (
    CompletionResponse,
    LLMProvider,
    Message,
    ToolDefinition,
    ToolResult,
)


class AgentContext(BaseModel):
    """Minimal context passed to an agent - key for token efficiency."""

    task_summary: str = Field(..., description="Brief summary of the current task")
    relevant_files: list[str] = Field(default_factory=list, description="Files relevant to task")
    previous_step_output: str | None = Field(default=None, description="Output from previous step")
    constraints: list[str] = Field(default_factory=list, description="Any constraints to follow")


class AgentResult(BaseModel):
    """Result from an agent execution."""

    success: bool
    output: str
    data: dict[str, Any] = Field(default_factory=dict, description="Structured output data")
    tokens_used: int | None = None
    summary_for_next_agent: str = Field(
        ..., description="Concise summary for the next agent in workflow"
    )


class BaseAgent(ABC):
    """Abstract base class for all agents.

    Key design principles for token efficiency:
    1. Minimal system prompts - only what this agent needs
    2. Focused context - receive only relevant information
    3. Summarized handoffs - pass summaries, not full history
    4. Tool filtering - only tools this agent can use
    """

    name: str = "BaseAgent"
    description: str = "Base agent"

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self._tools: list[ToolDefinition] = []
        self._tool_handlers: dict[str, Any] = {}

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent.

        Should be minimal and focused on this agent's specific role.
        """

    @abstractmethod
    def get_tools(self) -> list[ToolDefinition]:
        """Return tools available to this agent.

        Only include tools this specific agent needs.
        """

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Any,
    ) -> None:
        """Register a tool with its handler."""
        self._tools.append(
            ToolDefinition(name=name, description=description, parameters=parameters)
        )
        self._tool_handlers[name] = handler

    async def execute_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool and return its result."""
        handler = self._tool_handlers.get(name)
        if not handler:
            return ToolResult(
                tool_call_id=name,
                output="",
                error=f"Unknown tool: {name}",
            )

        try:
            result = await handler(**arguments)
            return ToolResult(tool_call_id=name, output=str(result))
        except Exception as e:
            return ToolResult(tool_call_id=name, output="", error=str(e))

    def build_messages(self, context: AgentContext, user_request: str) -> list[Message]:
        """Build the message list for this agent.

        Uses minimal context to reduce token usage.
        """
        messages = [Message(role="system", content=self.system_prompt)]

        # Add focused context
        context_text = self._format_context(context)
        if context_text:
            messages.append(Message(role="user", content=f"Context:\n{context_text}"))

        # Add the actual request
        messages.append(Message(role="user", content=user_request))

        return messages

    def _format_context(self, context: AgentContext) -> str:
        """Format context into minimal text."""
        parts = [f"Task: {context.task_summary}"]

        if context.relevant_files:
            parts.append(f"Relevant files: {', '.join(context.relevant_files)}")

        if context.previous_step_output:
            parts.append(f"Previous step output:\n{context.previous_step_output}")

        if context.constraints:
            parts.append(f"Constraints: {', '.join(context.constraints)}")

        return "\n".join(parts)

    async def run(self, context: AgentContext, request: str) -> AgentResult:
        """Execute the agent with given context and request.

        This is the main entry point for running an agent.
        """
        messages = self.build_messages(context, request)
        tools = self.get_tools()

        # Initial completion
        response = await self.provider.complete(messages, tools=tools if tools else None)

        # Handle tool calls in a loop
        tool_outputs: list[str] = []
        while response.tool_calls:
            for tool_call in response.tool_calls:
                result = await self.execute_tool(tool_call.name, tool_call.arguments)
                tool_outputs.append(f"{tool_call.name}: {result.output or result.error}")

                # Add tool result to messages
                messages.append(Message(role="assistant", content=response.content))
                messages.append(
                    Message(
                        role="user",
                        content=f"Tool result for {tool_call.name}:\n{result.output or result.error}",
                    )
                )

            # Get next response
            response = await self.provider.complete(messages, tools=tools if tools else None)

        # Process the final response
        return await self.process_response(response, tool_outputs)

    @abstractmethod
    async def process_response(
        self, response: CompletionResponse, tool_outputs: list[str]
    ) -> AgentResult:
        """Process the final LLM response into an AgentResult.

        Subclasses implement this to extract structured data.
        """

    def summarize_for_handoff(self, result: AgentResult) -> str:
        """Create a concise summary for the next agent.

        This is critical for token efficiency - we pass summaries,
        not full outputs between agents.
        """
        return result.summary_for_next_agent
