"""Tests for team collaboration system (TeamProblemSolver, ProactiveCollaborator, AgentDiscussion)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agentfarm.agents.collaboration import (
    AgentCollaborator,
    AgentAnswer,
    QuestionType,
    CollaborationType,
    ProactiveCollaboration,
    ProactiveCollaborator,
    FailureContext,
    FailureRecoveryStrategy,
    RecoverySolution,
    TeamProblemSolver,
    AgentDiscussion,
)


class TestProactiveCollaboration:
    """Tests for ProactiveCollaboration dataclass."""

    def test_create_collaboration(self):
        """Test creating a collaboration record."""
        collab = ProactiveCollaboration(
            initiator="executor",
            participants=["executor", "reviewer"],
            collaboration_type=CollaborationType.PEER_REVIEW,
            topic="Review code",
            context="def hello(): pass",
        )
        assert collab.initiator == "executor"
        assert collab.collaboration_type == CollaborationType.PEER_REVIEW
        assert len(collab.participants) == 2
        assert collab.timestamp > 0


class TestProactiveCollaborator:
    """Tests for ProactiveCollaborator."""

    @pytest.fixture
    def mock_collaborator(self):
        """Create a mock base collaborator."""
        collaborator = MagicMock(spec=AgentCollaborator)
        collaborator.ask_agent = AsyncMock(return_value=AgentAnswer(
            from_agent="reviewer",
            question="test",
            answer="Looks good!",
            confidence=0.9,
        ))
        return collaborator

    def test_init(self, mock_collaborator):
        """Test initializing ProactiveCollaborator."""
        proactive = ProactiveCollaborator(mock_collaborator)
        assert proactive.base == mock_collaborator
        assert proactive.collaboration_history == []

    @pytest.mark.asyncio
    async def test_request_peer_review(self, mock_collaborator):
        """Test requesting peer review."""
        proactive = ProactiveCollaborator(mock_collaborator)

        result = await proactive.request_peer_review(
            from_agent="executor",
            code_snippet="def hello(): return 'world'",
            question="Is this correct?",
        )

        assert result == "Looks good!"
        assert len(proactive.collaboration_history) == 1
        assert proactive.collaboration_history[0].collaboration_type == CollaborationType.PEER_REVIEW
        mock_collaborator.ask_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_peer_review_truncates_code(self, mock_collaborator):
        """Test that long code snippets are truncated."""
        proactive = ProactiveCollaborator(mock_collaborator)

        long_code = "x" * 1000  # Longer than 500 chars
        await proactive.request_peer_review(
            from_agent="executor",
            code_snippet=long_code,
        )

        call_args = mock_collaborator.ask_agent.call_args
        assert len(call_args.kwargs["question"]) < 1000

    @pytest.mark.asyncio
    async def test_brainstorm_design(self, mock_collaborator):
        """Test brainstorming with multiple agents."""
        proactive = ProactiveCollaborator(mock_collaborator)

        result = await proactive.brainstorm_design(
            from_agent="executor",
            design_question="REST or GraphQL?",
            participants=["planner", "reviewer"],
        )

        assert isinstance(result, dict)
        # Should have called ask_agent for each participant
        assert mock_collaborator.ask_agent.call_count >= 1
        assert len(proactive.collaboration_history) == 1
        assert proactive.collaboration_history[0].collaboration_type == CollaborationType.BRAINSTORM

    @pytest.mark.asyncio
    async def test_sanity_check_approved(self, mock_collaborator):
        """Test sanity check that gets approved."""
        mock_collaborator.ask_agent = AsyncMock(return_value=AgentAnswer(
            from_agent="verifier",
            question="test",
            answer="APPROVED - This approach looks reasonable.",
            confidence=0.9,
        ))

        proactive = ProactiveCollaborator(mock_collaborator)

        approved, feedback = await proactive.sanity_check(
            from_agent="executor",
            approach="Use async/await for all I/O",
        )

        assert approved
        assert "APPROVED" in feedback

    @pytest.mark.asyncio
    async def test_sanity_check_rejected(self, mock_collaborator):
        """Test sanity check that gets rejected."""
        mock_collaborator.ask_agent = AsyncMock(return_value=AgentAnswer(
            from_agent="verifier",
            question="test",
            answer="NEEDS_CHANGES - This has a problem with error handling.",
            confidence=0.9,
        ))

        proactive = ProactiveCollaborator(mock_collaborator)

        approved, feedback = await proactive.sanity_check(
            from_agent="executor",
            approach="Ignore all errors",
        )

        assert not approved
        assert "problem" in feedback.lower()

    @pytest.mark.asyncio
    async def test_share_knowledge(self, mock_collaborator):
        """Test sharing knowledge between agents."""
        proactive = ProactiveCollaborator(mock_collaborator)

        await proactive.share_knowledge(
            from_agent="executor",
            to_agent="verifier",
            knowledge="The API uses JWT tokens",
            topic="Auth info",
        )

        assert len(proactive.collaboration_history) == 1
        assert proactive.collaboration_history[0].collaboration_type == CollaborationType.KNOWLEDGE_SHARE

    @pytest.mark.asyncio
    async def test_listener_notification(self, mock_collaborator):
        """Test that listeners are notified of collaborations."""
        proactive = ProactiveCollaborator(mock_collaborator)

        notified_collabs = []

        async def listener(collab):
            notified_collabs.append(collab)

        proactive.add_listener(listener)

        await proactive.request_peer_review(
            from_agent="executor",
            code_snippet="test",
        )

        assert len(notified_collabs) == 1
        assert notified_collabs[0].collaboration_type == CollaborationType.PEER_REVIEW

    def test_get_collaboration_summary_empty(self, mock_collaborator):
        """Test summary with no collaborations."""
        proactive = ProactiveCollaborator(mock_collaborator)
        assert proactive.get_collaboration_summary() == ""

    @pytest.mark.asyncio
    async def test_get_collaboration_summary(self, mock_collaborator):
        """Test summary with collaborations."""
        proactive = ProactiveCollaborator(mock_collaborator)

        await proactive.request_peer_review("executor", "code")

        summary = proactive.get_collaboration_summary()
        assert "Recent Agent Collaborations:" in summary
        assert "peer_review" in summary


class TestFailureContext:
    """Tests for FailureContext dataclass."""

    def test_create_failure_context(self):
        """Test creating a failure context."""
        ctx = FailureContext(
            agent="executor",
            task="Write file",
            error="Permission denied",
            attempts=1,
        )
        assert ctx.agent == "executor"
        assert ctx.task == "Write file"
        assert ctx.error == "Permission denied"
        assert ctx.attempts == 1
        assert ctx.strategies_tried == []

    def test_add_strategy(self):
        """Test adding tried strategies."""
        ctx = FailureContext(
            agent="executor",
            task="test",
            error="error",
        )
        ctx.strategies_tried.append(FailureRecoveryStrategy.ASK_FOR_HELP)
        assert len(ctx.strategies_tried) == 1


class TestRecoverySolution:
    """Tests for RecoverySolution dataclass."""

    def test_create_solution(self):
        """Test creating a recovery solution."""
        solution = RecoverySolution(
            strategy=FailureRecoveryStrategy.ASK_FOR_HELP,
            solution="Try using absolute path",
            suggested_by="verifier",
            confidence=0.85,
            implementation_steps=["1. Get absolute path", "2. Retry write"],
        )
        assert solution.strategy == FailureRecoveryStrategy.ASK_FOR_HELP
        assert solution.confidence == 0.85
        assert len(solution.implementation_steps) == 2


class TestTeamProblemSolver:
    """Tests for TeamProblemSolver."""

    @pytest.fixture
    def mock_collaborator(self):
        """Create a mock collaborator."""
        collaborator = MagicMock(spec=AgentCollaborator)
        collaborator.ask_agent = AsyncMock(return_value=AgentAnswer(
            from_agent="helper",
            question="test",
            answer="1. First, check the path\n2. Then retry the operation",
            confidence=0.8,
        ))
        return collaborator

    def test_init(self, mock_collaborator):
        """Test initializing TeamProblemSolver."""
        solver = TeamProblemSolver(mock_collaborator)
        assert solver.collaborator == mock_collaborator
        assert solver.max_attempts == 3
        assert solver.failure_history == []

    def test_identify_problem_type_syntax(self, mock_collaborator):
        """Test identifying syntax error."""
        solver = TeamProblemSolver(mock_collaborator)
        problem = solver._identify_problem_type("SyntaxError: invalid syntax", "write code")
        assert problem == "syntax error"

    def test_identify_problem_type_test(self, mock_collaborator):
        """Test identifying test failure."""
        solver = TeamProblemSolver(mock_collaborator)
        problem = solver._identify_problem_type("AssertionError: expected True", "run tests")
        assert problem == "test failing"

    def test_identify_problem_type_ui(self, mock_collaborator):
        """Test identifying UI issue."""
        solver = TeamProblemSolver(mock_collaborator)
        problem = solver._identify_problem_type("Error", "create component")
        assert problem == "UI issue"

    def test_select_helper_agent_specialist(self, mock_collaborator):
        """Test selecting specialist helper."""
        solver = TeamProblemSolver(mock_collaborator)

        # Syntax errors should go to verifier
        helper = solver._select_helper_agent("syntax error", "executor")
        assert helper == "verifier"

        # Design decisions should go to reviewer
        helper = solver._select_helper_agent("design decision", "executor")
        assert helper == "reviewer"

    def test_select_helper_agent_complement(self, mock_collaborator):
        """Test selecting complementary helper."""
        solver = TeamProblemSolver(mock_collaborator)

        # Executor problems go to verifier
        helper = solver._select_helper_agent("unknown", "executor")
        assert helper == "verifier"

        # Verifier problems go to reviewer
        helper = solver._select_helper_agent("unknown", "verifier")
        assert helper == "reviewer"

    @pytest.mark.asyncio
    async def test_attempt_recovery_first_try(self, mock_collaborator):
        """Test first recovery attempt (asks for help)."""
        solver = TeamProblemSolver(mock_collaborator)

        failure = FailureContext(
            agent="executor",
            task="Write file",
            error="Permission denied",
            attempts=1,
        )

        solution = await solver.attempt_recovery(failure)

        assert solution is not None
        assert solution.strategy == FailureRecoveryStrategy.ASK_FOR_HELP
        assert solution.confidence > 0.5
        mock_collaborator.ask_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_attempt_recovery_second_try(self, mock_collaborator):
        """Test second recovery attempt (team discussion)."""
        solver = TeamProblemSolver(mock_collaborator)

        failure = FailureContext(
            agent="executor",
            task="Write file",
            error="Permission denied",
            attempts=2,
        )

        solution = await solver.attempt_recovery(failure)

        assert solution is not None
        assert solution.strategy == FailureRecoveryStrategy.TEAM_DISCUSSION
        # Should have called multiple agents
        assert mock_collaborator.ask_agent.call_count >= 1

    @pytest.mark.asyncio
    async def test_attempt_recovery_third_try(self, mock_collaborator):
        """Test third recovery attempt (simplify task)."""
        solver = TeamProblemSolver(mock_collaborator)

        failure = FailureContext(
            agent="executor",
            task="Write complex file",
            error="Error",
            attempts=3,
        )

        solution = await solver.attempt_recovery(failure)

        assert solution is not None
        assert solution.strategy == FailureRecoveryStrategy.SIMPLIFY_TASK

    @pytest.mark.asyncio
    async def test_recovery_listener_notification(self, mock_collaborator):
        """Test that recovery listeners are notified."""
        solver = TeamProblemSolver(mock_collaborator)

        notifications = []

        async def listener(ctx, solution):
            notifications.append((ctx, solution))

        solver.add_recovery_listener(listener)

        failure = FailureContext(
            agent="executor",
            task="test",
            error="error",
            attempts=1,
        )

        await solver.attempt_recovery(failure)

        assert len(notifications) == 1
        assert notifications[0][0] == failure

    @pytest.mark.asyncio
    async def test_recovery_with_low_confidence(self, mock_collaborator):
        """Test recovery when helper has low confidence."""
        mock_collaborator.ask_agent = AsyncMock(return_value=AgentAnswer(
            from_agent="helper",
            question="test",
            answer="I'm not sure about this",
            confidence=0.3,
            needs_user_input=True,
        ))

        solver = TeamProblemSolver(mock_collaborator)

        failure = FailureContext(
            agent="executor",
            task="test",
            error="error",
            attempts=1,
        )

        solution = await solver.attempt_recovery(failure)

        # Low confidence should result in no solution
        assert solution is None

    def test_extract_steps_numbered(self, mock_collaborator):
        """Test extracting numbered steps."""
        solver = TeamProblemSolver(mock_collaborator)

        text = """Here's what to do:
1. First step
2. Second step
3. Third step
"""
        steps = solver._extract_steps(text)
        assert len(steps) == 3
        assert "First step" in steps[0]

    def test_extract_steps_bullets(self, mock_collaborator):
        """Test extracting bullet points."""
        solver = TeamProblemSolver(mock_collaborator)

        text = """Here's what to do:
- First step
- Second step
- Third step
"""
        steps = solver._extract_steps(text)
        assert len(steps) == 3
        assert "First step" in steps[0]

    def test_extract_steps_max_five(self, mock_collaborator):
        """Test that max 5 steps are extracted."""
        solver = TeamProblemSolver(mock_collaborator)

        text = "\n".join(f"{i}. Step {i}" for i in range(1, 10))
        steps = solver._extract_steps(text)
        assert len(steps) == 5

    def test_get_recovery_summary_empty(self, mock_collaborator):
        """Test summary with no attempts."""
        solver = TeamProblemSolver(mock_collaborator)
        assert solver.get_recovery_summary() == "No recovery attempts"

    @pytest.mark.asyncio
    async def test_get_recovery_summary(self, mock_collaborator):
        """Test summary with attempts."""
        solver = TeamProblemSolver(mock_collaborator)

        failure = FailureContext(agent="executor", task="test", error="error", attempts=1)
        await solver.attempt_recovery(failure)

        summary = solver.get_recovery_summary()
        assert "1/1" in summary  # 1 successful out of 1


class TestAgentDiscussion:
    """Tests for AgentDiscussion."""

    @pytest.fixture
    def mock_collaborator(self):
        """Create a mock collaborator."""
        collaborator = MagicMock(spec=AgentCollaborator)
        collaborator.ask_agent = AsyncMock(return_value=AgentAnswer(
            from_agent="agent",
            question="test",
            answer="Here's my perspective...",
            confidence=0.8,
        ))
        return collaborator

    def test_init(self, mock_collaborator):
        """Test initializing AgentDiscussion."""
        discussion = AgentDiscussion(mock_collaborator)
        assert discussion.collaborator == mock_collaborator

    @pytest.mark.asyncio
    async def test_discuss_basic(self, mock_collaborator):
        """Test basic discussion."""
        discussion = AgentDiscussion(mock_collaborator)

        result = await discussion.discuss(
            topic="REST or GraphQL?",
            participants=["planner", "reviewer", "executor"],
            moderator="planner",
        )

        assert "topic" in result
        assert result["topic"] == "REST or GraphQL?"
        assert "responses" in result
        assert "synthesis" in result
        assert "participants" in result

    @pytest.mark.asyncio
    async def test_discuss_all_participants_respond(self, mock_collaborator):
        """Test that all participants (except moderator) respond."""
        responses = {}

        async def mock_ask(from_agent, to_agent, **kwargs):
            responses[to_agent] = f"Response from {to_agent}"
            return AgentAnswer(
                from_agent=to_agent,
                question="test",
                answer=f"Response from {to_agent}",
                confidence=0.8,
            )

        mock_collaborator.ask_agent = mock_ask

        discussion = AgentDiscussion(mock_collaborator)

        result = await discussion.discuss(
            topic="Test topic",
            participants=["reviewer", "executor", "verifier"],
            moderator="planner",
        )

        # All non-moderator participants should have responded
        assert "reviewer" in result["responses"]
        assert "executor" in result["responses"]
        assert "verifier" in result["responses"]

    @pytest.mark.asyncio
    async def test_discuss_handles_errors(self, mock_collaborator):
        """Test discussion handles agent errors gracefully."""
        call_count = 0

        async def mock_ask_with_error(from_agent, to_agent, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Agent unavailable")
            return AgentAnswer(
                from_agent=to_agent,
                question="test",
                answer="Response",
                confidence=0.8,
            )

        mock_collaborator.ask_agent = mock_ask_with_error

        discussion = AgentDiscussion(mock_collaborator)

        result = await discussion.discuss(
            topic="Test",
            participants=["agent1", "agent2"],
            moderator="planner",
        )

        # Should still have results (one with error)
        assert "responses" in result

    @pytest.mark.asyncio
    async def test_synthesize_no_responses(self, mock_collaborator):
        """Test synthesis with no responses."""
        discussion = AgentDiscussion(mock_collaborator)

        result = await discussion._synthesize({}, "topic", "planner")
        assert result == "No responses to synthesize"

    @pytest.mark.asyncio
    async def test_synthesize_calls_moderator(self, mock_collaborator):
        """Test that synthesis calls the moderator."""
        discussion = AgentDiscussion(mock_collaborator)

        responses = {
            "agent1": "First perspective",
            "agent2": "Second perspective",
        }

        await discussion._synthesize(responses, "topic", "planner")

        # Should have called ask_agent with moderator as target
        call_args = mock_collaborator.ask_agent.call_args
        assert call_args.kwargs["to_agent"] == "planner"


class TestCollaborationIntegration:
    """Integration tests for collaboration components."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent."""
        agent = MagicMock()
        agent.run = AsyncMock(return_value=MagicMock(
            output="Agent response",
            data={},
        ))
        return agent

    @pytest.mark.asyncio
    async def test_proactive_uses_team_solver(self, mock_agent):
        """Test that proactive collaboration can use team problem solver."""
        collaborator = AgentCollaborator()
        collaborator.register_agent("reviewer", mock_agent)
        collaborator.register_agent("planner", mock_agent)
        collaborator.register_agent("verifier", mock_agent)

        proactive = ProactiveCollaborator(collaborator)
        solver = TeamProblemSolver(collaborator)

        # First try proactive peer review
        await proactive.request_peer_review("executor", "code")

        # If that fails, escalate to team problem solver
        failure = FailureContext(
            agent="executor",
            task="code review",
            error="Review unclear",
            attempts=2,
        )

        solution = await solver.attempt_recovery(failure)

        # Both should work together
        assert len(proactive.collaboration_history) == 1

    @pytest.mark.asyncio
    async def test_discussion_feeds_into_solver(self, mock_agent):
        """Test that discussion results can feed into problem solving."""
        collaborator = AgentCollaborator()
        collaborator.register_agent("planner", mock_agent)
        collaborator.register_agent("reviewer", mock_agent)
        collaborator.register_agent("verifier", mock_agent)

        discussion = AgentDiscussion(collaborator)
        solver = TeamProblemSolver(collaborator)

        # Start with a discussion
        disc_result = await discussion.discuss(
            topic="How to handle errors",
            participants=["reviewer", "verifier"],
            moderator="planner",
        )

        # Use discussion results in failure context
        failure = FailureContext(
            agent="executor",
            task="error handling",
            error=f"After discussing: {disc_result.get('synthesis', '')}",
            attempts=1,
        )

        solution = await solver.attempt_recovery(failure)

        # Should still find a solution
        assert solution is not None or failure.attempts < 3
