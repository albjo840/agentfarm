from __future__ import annotations

"""Base agent class with token-efficient context management."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from agentfarm.providers.base import (
    CompletionResponse,
    LLMProvider,
    Message,
    ToolDefinition,
    ToolResult,
)

if TYPE_CHECKING:
    from agentfarm.memory.base import MemoryManager
    from agentfarm.agents.collaboration import AgentCollaborator


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
    5. Memory integration - optional short/long-term memory
    6. Agent collaboration - ask other agents, not the user
    """

    name: str = "BaseAgent"
    description: str = "Base agent"

    def __init__(
        self,
        provider: LLMProvider,
        memory: MemoryManager | None = None,
        collaborator: AgentCollaborator | None = None,
    ) -> None:
        self.provider = provider
        self.memory = memory
        self.collaborator = collaborator
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

        # Include memory summary if available
        if self.memory:
            memory_context = self.memory.get_context_summary(max_entries=5)
            if memory_context:
                parts.append(f"\n{memory_context}")

        return "\n".join(parts)

    def remember(self, key: str, value: str, long_term: bool = False) -> None:
        """Store information in memory.

        Args:
            key: Identifier for the memory
            value: Information to store
            long_term: If True, persist across sessions
        """
        if self.memory:
            self.memory.store(key, value, long_term=long_term)

    def recall(self, key: str) -> str | None:
        """Retrieve information from memory.

        Args:
            key: Memory key to retrieve

        Returns:
            Stored value or None if not found
        """
        if self.memory:
            return self.memory.retrieve(key)
        return None

    def search_memory(self, query: str, limit: int = 5) -> list[str]:
        """Search memory for relevant information.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of relevant memory values
        """
        if self.memory:
            entries = self.memory.search(query, limit)
            return [entry.value for entry in entries]
        return []

    async def ask_agent(self, agent_name: str, question: str, context: str = "") -> str:
        """Ask another agent a question.

        Use this instead of asking the user. Only escalate to orchestrator
        if absolutely necessary.

        Args:
            agent_name: Name of the agent to ask (planner, executor, verifier, reviewer, designer)
            question: The question to ask
            context: Additional context

        Returns:
            The agent's answer
        """
        if not self.collaborator:
            return f"Collaboration not available. Making best judgment for: {question}"

        from agentfarm.agents.collaboration import QuestionType

        answer = await self.collaborator.ask_agent(
            from_agent=self.name.lower().replace("agent", ""),
            to_agent=agent_name,
            question=question,
            question_type=QuestionType.CLARIFICATION,
            context=context,
        )

        if answer.needs_user_input:
            # Escalate to orchestrator
            return f"ESCALATE: {answer.answer}"

        return answer.answer

    async def escalate_to_orchestrator(self, question: str, reason: str) -> str:
        """Escalate a question to the orchestrator (who can ask the user).

        Use this when you absolutely need user input.

        Args:
            question: The question that needs user input
            reason: Why you need to escalate

        Returns:
            The orchestrator's response (or user's answer)
        """
        if not self.collaborator:
            return f"Escalation not available. Making best judgment for: {question}"

        from agentfarm.agents.collaboration import QuestionType

        answer = await self.collaborator.ask_agent(
            from_agent=self.name.lower().replace("agent", ""),
            to_agent="orchestrator",
            question=f"{question}\n\nReason for escalation: {reason}",
            question_type=QuestionType.CLARIFICATION,
        )

        return answer.answer

    def set_collaborator(self, collaborator: AgentCollaborator) -> None:
        """Set the collaborator for inter-agent communication."""
        self.collaborator = collaborator

        # Register collaboration tools
        self._register_collaboration_tools()

    def _register_collaboration_tools(self) -> None:
        """Register tools for collaborating with other agents."""
        if not self.collaborator:
            return

        agent_id = self.name.lower().replace("agent", "")

        # Add ask_agent tools for other agents
        for target in ["planner", "executor", "verifier", "reviewer", "designer"]:
            if target == agent_id:
                continue

            async def ask_handler(question: str, context: str = "", target_agent: str = target) -> str:
                return await self.ask_agent(target_agent, question, context)

            self._tool_handlers[f"ask_{target}"] = ask_handler

        # Add escalation tool
        async def escalate_handler(question: str, reason: str) -> str:
            return await self.escalate_to_orchestrator(question, reason)

        self._tool_handlers["escalate_to_orchestrator"] = escalate_handler

    async def run(
        self,
        context: AgentContext,
        request: str,
        max_tool_calls: int = 10,
    ) -> AgentResult:
        """Execute the agent with given context and request.

        This is the main entry point for running an agent.

        Args:
            context: Minimal context for the agent
            request: The user's request
            max_tool_calls: Maximum number of tool call rounds to prevent infinite loops
        """
        messages = self.build_messages(context, request)
        tools = self.get_tools()

        # Initial completion
        response = await self.provider.complete(messages, tools=tools if tools else None)

        # Handle tool calls in a loop with a limit
        tool_outputs: list[str] = []
        tool_call_count = 0

        while response.tool_calls and tool_call_count < max_tool_calls:
            tool_call_count += 1

            for tool_call in response.tool_calls:
                result = await self.execute_tool(tool_call.name, tool_call.arguments)
                tool_outputs.append(f"{tool_call.name}: {result.output or result.error}")

                # Add tool result to messages
                messages.append(Message(role="assistant", content=response.content or ""))
                messages.append(
                    Message(
                        role="user",
                        content=f"Tool result for {tool_call.name}:\n{result.output or result.error}",
                    )
                )

            # Check if we've hit the limit
            if tool_call_count >= max_tool_calls:
                # Force final response without tools
                response = await self.provider.complete(messages, tools=None)
                break

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
