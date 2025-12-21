"""Tests for the agent collaboration system."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agentfarm.agents.collaboration import (
    AgentCollaborator,
    AgentQuestion,
    AgentAnswer,
    QuestionType,
    CollaborationSession,
)
from agentfarm.agents.base import AgentContext, AgentResult


class TestCollaborationSession:
    """Tests for CollaborationSession."""

    def test_empty_session(self):
        """Test empty collaboration session."""
        session = CollaborationSession()
        assert session.exchanges == []
        assert session.user_escalations == []
        assert session.get_summary() == ""

    def test_add_exchange(self):
        """Test adding an exchange."""
        session = CollaborationSession()
        q = AgentQuestion(
            from_agent="executor",
            to_agent="planner",
            question="How should I implement this?",
            question_type=QuestionType.TECHNICAL,
        )
        a = AgentAnswer(
            from_agent="planner",
            question="How should I implement this?",
            answer="Use the existing pattern from utils.py",
        )
        session.add_exchange(q, a)
        assert len(session.exchanges) == 1
        assert session.exchanges[0] == (q, a)

    def test_get_summary(self):
        """Test getting a summary of collaboration."""
        session = CollaborationSession()
        q = AgentQuestion(
            from_agent="executor",
            to_agent="planner",
            question="How should I implement this feature?",
            question_type=QuestionType.TECHNICAL,
        )
        a = AgentAnswer(
            from_agent="planner",
            question="How should I implement this feature?",
            answer="Use async/await pattern for all I/O operations",
        )
        session.add_exchange(q, a)

        summary = session.get_summary()
        assert "Agent Collaboration:" in summary
        assert "executor→planner" in summary


class TestAgentQuestion:
    """Tests for AgentQuestion."""

    def test_create_question(self):
        """Test creating a question."""
        q = AgentQuestion(
            from_agent="executor",
            to_agent="verifier",
            question="How do I run the tests?",
            question_type=QuestionType.VERIFICATION,
            context="Working on authentication feature",
        )
        assert q.from_agent == "executor"
        assert q.to_agent == "verifier"
        assert q.question == "How do I run the tests?"
        assert q.question_type == QuestionType.VERIFICATION
        assert q.context == "Working on authentication feature"


class TestAgentAnswer:
    """Tests for AgentAnswer."""

    def test_create_answer(self):
        """Test creating an answer."""
        a = AgentAnswer(
            from_agent="verifier",
            question="How do I run the tests?",
            answer="Run pytest tests/ -v",
            confidence=0.95,
        )
        assert a.from_agent == "verifier"
        assert a.answer == "Run pytest tests/ -v"
        assert a.confidence == 0.95
        assert not a.needs_user_input

    def test_answer_needs_user_input(self):
        """Test answer that needs user input."""
        a = AgentAnswer(
            from_agent="planner",
            question="What framework?",
            answer="NEED_USER_INPUT: Multiple options available",
            confidence=0.3,
            needs_user_input=True,
        )
        assert a.needs_user_input


class TestAgentCollaborator:
    """Tests for AgentCollaborator."""

    def test_register_agent(self):
        """Test registering an agent."""
        collaborator = AgentCollaborator()
        mock_agent = MagicMock()
        collaborator.register_agent("planner", mock_agent)
        assert "planner" in collaborator._agents
        assert collaborator._agents["planner"] == mock_agent

    def test_register_multiple_agents(self):
        """Test registering multiple agents at once."""
        collaborator = AgentCollaborator()
        agents = {
            "planner": MagicMock(),
            "executor": MagicMock(),
            "verifier": MagicMock(),
        }
        collaborator.register_agents(agents)
        assert len(collaborator._agents) == 3

    @pytest.mark.asyncio
    async def test_ask_agent_not_found(self):
        """Test asking a non-existent agent."""
        collaborator = AgentCollaborator()
        answer = await collaborator.ask_agent(
            from_agent="executor",
            to_agent="nonexistent",
            question="Hello?",
        )
        assert "not available" in answer.answer
        assert answer.confidence == 0.0
        assert answer.needs_user_input

    @pytest.mark.asyncio
    async def test_ask_user_only_orchestrator(self):
        """Test that only orchestrator can ask user."""
        collaborator = AgentCollaborator()
        with pytest.raises(ValueError) as exc_info:
            await collaborator.ask_user("Question?", from_agent="executor")
        assert "cannot ask user directly" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_ask_user_orchestrator_allowed(self):
        """Test that orchestrator can ask user."""
        async def user_callback(question: str) -> str:
            return "User's answer"

        collaborator = AgentCollaborator(user_callback=user_callback)
        answer = await collaborator.ask_user("What framework?", from_agent="orchestrator")
        assert answer == "User's answer"

    def test_get_collaboration_context_empty(self):
        """Test getting context with no collaboration."""
        collaborator = AgentCollaborator()
        assert collaborator.get_collaboration_context() == ""

    def test_estimate_confidence_high(self):
        """Test confidence estimation for confident answer."""
        collaborator = AgentCollaborator()
        confidence = collaborator._estimate_confidence("Use async/await pattern.")
        assert confidence == 0.9

    def test_estimate_confidence_low(self):
        """Test confidence estimation for uncertain answer."""
        collaborator = AgentCollaborator()
        confidence = collaborator._estimate_confidence("I'm not sure, might be a bug.")
        assert confidence == 0.5

    def test_needs_user_input_true(self):
        """Test detecting need for user input."""
        collaborator = AgentCollaborator()
        assert collaborator._needs_user_input("NEED_USER_INPUT: Cannot determine")
        assert collaborator._needs_user_input("need_user_input required")

    def test_needs_user_input_false(self):
        """Test when user input not needed."""
        collaborator = AgentCollaborator()
        assert not collaborator._needs_user_input("Use the standard pattern.")
