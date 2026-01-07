"""Agent collaboration system for inter-agent communication.

This module enables agents to consult each other instead of asking the user.
Only the orchestrator should communicate directly with the user.

Includes recursion protection to prevent infinite agent loops.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Awaitable
from enum import Enum

if TYPE_CHECKING:
    from agentfarm.agents.base import BaseAgent, RecursionGuard

logger = logging.getLogger(__name__)


class QuestionType(Enum):
    """Types of questions agents can ask each other."""
    CLARIFICATION = "clarification"  # Need more info about the task
    TECHNICAL = "technical"          # Technical implementation question
    DESIGN = "design"                # Design/architecture decision
    VERIFICATION = "verification"    # Verify an approach/solution


@dataclass
class AgentQuestion:
    """A question from one agent to another."""
    from_agent: str
    to_agent: str
    question: str
    question_type: QuestionType
    context: str = ""  # Additional context


@dataclass
class AgentAnswer:
    """An answer from one agent to another."""
    from_agent: str
    question: str
    answer: str
    confidence: float = 1.0  # 0.0-1.0, how confident the agent is
    needs_user_input: bool = False  # If True, escalate to orchestrator


@dataclass
class CollaborationSession:
    """Tracks collaboration between agents during a workflow."""
    exchanges: list[tuple[AgentQuestion, AgentAnswer]] = field(default_factory=list)
    user_escalations: list[str] = field(default_factory=list)

    def add_exchange(self, question: AgentQuestion, answer: AgentAnswer) -> None:
        self.exchanges.append((question, answer))

    def get_summary(self) -> str:
        """Get a token-efficient summary of collaboration."""
        if not self.exchanges:
            return ""

        lines = ["Agent Collaboration:"]
        for q, a in self.exchanges[-3:]:  # Only last 3 to save tokens
            lines.append(f"  {q.from_agent}→{q.to_agent}: {q.question[:50]}...")
            lines.append(f"    Answer: {a.answer[:50]}...")
        return "\n".join(lines)


class AgentCollaborator:
    """Enables inter-agent communication.

    Key principles:
    1. Agents can ask each other questions
    2. Only orchestrator asks user questions
    3. If an agent can't answer, it escalates to orchestrator
    4. All exchanges are logged for context
    5. Recursion protection prevents infinite loops
    """

    def __init__(
        self,
        user_callback: Callable[[str], Awaitable[str]] | None = None,
        recursion_guard: RecursionGuard | None = None,
    ):
        self._agents: dict[str, BaseAgent] = {}
        self._session = CollaborationSession()
        self._user_callback = user_callback  # For orchestrator to ask user
        self._recursion_guard = recursion_guard

    def set_recursion_guard(self, guard: RecursionGuard) -> None:
        """Set or update the recursion guard."""
        self._recursion_guard = guard
        # Also set on all registered agents
        for agent in self._agents.values():
            agent.set_recursion_guard(guard)

    def register_agent(self, name: str, agent: BaseAgent) -> None:
        """Register an agent for collaboration."""
        self._agents[name] = agent
        # Share recursion guard with new agent
        if self._recursion_guard:
            agent.set_recursion_guard(self._recursion_guard)

    def register_agents(self, agents: dict[str, BaseAgent]) -> None:
        """Register multiple agents at once."""
        for name, agent in agents.items():
            self.register_agent(name, agent)

    async def ask_agent(
        self,
        from_agent: str,
        to_agent: str,
        question: str,
        question_type: QuestionType = QuestionType.CLARIFICATION,
        context: str = "",
    ) -> AgentAnswer:
        """Ask another agent a question.

        Args:
            from_agent: Name of the asking agent
            to_agent: Name of the agent to ask
            question: The question to ask
            question_type: Type of question
            context: Additional context for the question

        Returns:
            AgentAnswer with the response
        """
        from agentfarm.agents.base import AgentContext, RecursionGuard, RecursionLimitError

        q = AgentQuestion(
            from_agent=from_agent,
            to_agent=to_agent,
            question=question,
            question_type=question_type,
            context=context,
        )

        # Get the target agent
        target = self._agents.get(to_agent)
        if not target:
            # If agent not found, return a helpful error
            answer = AgentAnswer(
                from_agent=to_agent,
                question=question,
                answer=f"Agent '{to_agent}' not available. Available agents: {list(self._agents.keys())}",
                confidence=0.0,
                needs_user_input=True,
            )
            self._session.add_exchange(q, answer)
            return answer

        # Build a focused context for the question
        ctx = AgentContext(
            task_summary=f"Answer question from {from_agent}",
            previous_step_output=context,
        )

        # Format the question for the agent
        formatted_question = self._format_question_for_agent(q)

        # Use existing guard or create a new one
        guard = self._recursion_guard or RecursionGuard()

        try:
            # Pass the recursion guard to the nested agent call
            result = await target.run(
                ctx,
                formatted_question,
                recursion_guard=guard,
            )

            # Check if result indicates recursion was stopped
            if result.data.get("error") == "recursion_limit":
                logger.warning(
                    "Recursion limit prevented %s from answering %s's question",
                    to_agent,
                    from_agent,
                )
                answer = AgentAnswer(
                    from_agent=to_agent,
                    question=question,
                    answer=f"Cannot answer: recursion limit reached. {result.output}",
                    confidence=0.0,
                    needs_user_input=True,
                )
            else:
                # Parse the answer
                answer = AgentAnswer(
                    from_agent=to_agent,
                    question=question,
                    answer=result.output,
                    confidence=self._estimate_confidence(result.output),
                    needs_user_input=self._needs_user_input(result.output),
                )

        except RecursionLimitError as e:
            logger.error("Recursion limit in ask_agent: %s", e)
            answer = AgentAnswer(
                from_agent=to_agent,
                question=question,
                answer=f"Cannot answer: {e}. Consider simplifying the task or breaking it into smaller steps.",
                confidence=0.0,
                needs_user_input=True,
            )
        except Exception as e:
            logger.exception("Error in ask_agent from %s to %s", from_agent, to_agent)
            answer = AgentAnswer(
                from_agent=to_agent,
                question=question,
                answer=f"Error consulting {to_agent}: {str(e)}",
                confidence=0.0,
                needs_user_input=True,
            )

        self._session.add_exchange(q, answer)
        return answer

    async def ask_user(self, question: str, from_agent: str = "orchestrator") -> str:
        """Ask the user a question (only orchestrator should call this).

        Args:
            question: Question to ask the user
            from_agent: Agent asking (for logging)

        Returns:
            User's answer
        """
        if from_agent != "orchestrator":
            # Non-orchestrator agents should escalate, not ask directly
            raise ValueError(
                f"Agent '{from_agent}' cannot ask user directly. "
                "Escalate to orchestrator instead."
            )

        self._session.user_escalations.append(question)

        if self._user_callback:
            return await self._user_callback(question)

        # If no callback, return a default
        return "User callback not configured. Proceeding with best judgment."

    def get_collaboration_context(self) -> str:
        """Get collaboration summary for agent context."""
        return self._session.get_summary()

    def _format_question_for_agent(self, q: AgentQuestion) -> str:
        """Format a question for an agent to answer."""
        parts = [
            f"{q.from_agent} is asking you ({q.to_agent}) a {q.question_type.value} question:",
            "",
            q.question,
        ]

        if q.context:
            parts.extend(["", "Context:", q.context])

        parts.extend([
            "",
            "Provide a direct, concise answer. If you're not sure or need user input,",
            "say 'NEED_USER_INPUT: <reason>'.",
        ])

        return "\n".join(parts)

    def _estimate_confidence(self, output: str) -> float:
        """Estimate confidence based on output."""
        # Simple heuristics
        low_confidence_signals = [
            "not sure", "uncertain", "might", "could be", "possibly",
            "NEED_USER_INPUT", "ask the user", "unclear",
        ]

        output_lower = output.lower()
        for signal in low_confidence_signals:
            if signal.lower() in output_lower:
                return 0.5

        return 0.9

    def _needs_user_input(self, output: str) -> bool:
        """Check if the answer requires user input."""
        return "NEED_USER_INPUT" in output.upper()


# Collaboration tools for agents
def create_collaboration_tools(
    collaborator: AgentCollaborator,
    current_agent: str,
) -> list[dict[str, Any]]:
    """Create collaboration tools for an agent.

    These tools let agents ask each other questions.
    """
    tools = []

    # Only include tools for other agents
    for agent_name in ["planner", "executor", "verifier", "reviewer", "designer"]:
        if agent_name == current_agent:
            continue

        tools.append({
            "name": f"ask_{agent_name}",
            "description": f"Ask the {agent_name} agent a question for clarification or collaboration",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask",
                    },
                    "context": {
                        "type": "string",
                        "description": "Additional context for the question",
                    },
                },
                "required": ["question"],
            },
        })

    # Orchestrator can ask user
    if current_agent == "orchestrator":
        tools.append({
            "name": "ask_user",
            "description": "Ask the user for clarification (ONLY use when absolutely necessary)",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask the user",
                    },
                },
                "required": ["question"],
            },
        })
    else:
        # Other agents can escalate to orchestrator
        tools.append({
            "name": "escalate_to_orchestrator",
            "description": "Escalate a question to the orchestrator if you need user input",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question that needs user input",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why you need to escalate",
                    },
                },
                "required": ["question", "reason"],
            },
        })

    return tools
