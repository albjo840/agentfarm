"""Testing tool handler for MCP integration.

This module provides tools for testing individual agents, workflow phases,
and running quick sanity checks on AgentFarm components.
"""

from __future__ import annotations

import json
import time

from .schemas import AgentTestResult


class TestingToolHandler:
    """Handler for testing AgentFarm agents and workflow phases.

    This class provides methods to test individual agents, run specific
    workflow phases, and execute quick sanity checks on system components.

    Attributes:
        working_dir: The working directory for agent operations.
    """

    def __init__(self, working_dir: str) -> None:
        """Initialize the testing tool handler.

        Args:
            working_dir: The working directory where agents will operate.
        """
        self.working_dir = working_dir

    async def test_agent(
        self, agent: str, task: str, context_files: list | None = None
    ) -> str:
        """Test a specific agent with a given task.

        Runs an individual agent (planner, executor, verifier, or reviewer)
        with the provided task and context files, returning the result.

        Args:
            agent: The name of the agent to test. Must be one of:
                'planner', 'executor', 'verifier', 'reviewer'.
            task: The task description to pass to the agent.
            context_files: Optional list of file paths to include as context.

        Returns:
            JSON string containing an AgentTestResult with:
                - agent: Name of the tested agent
                - success: Whether the agent completed successfully
                - output: First 1000 chars of agent output
                - summary: Summary for the next agent
                - tokens_used: Number of tokens consumed
                - duration_seconds: Time taken to run

            On error, returns JSON with 'error' and 'duration_seconds' keys.
        """
        from agentfarm.agents.base import AgentContext
        from agentfarm.orchestrator import Orchestrator

        start = time.time()
        try:
            orchestrator = Orchestrator(
                provider=None, working_dir=self.working_dir, use_multi_provider=True
            )

            agent_map = {
                "planner": orchestrator.planner,
                "executor": orchestrator.executor,
                "verifier": orchestrator.verifier,
                "reviewer": orchestrator.reviewer,
            }
            agent_instance = agent_map.get(agent.lower())
            if not agent_instance:
                return json.dumps({"error": f"Unknown agent: {agent}"})

            context = AgentContext(
                task_summary=task,
                relevant_files=context_files or [],
                working_dir=self.working_dir,
            )
            result = await agent_instance.run(context)

            return json.dumps(
                AgentTestResult(
                    agent=agent,
                    success=result.success,
                    output=result.output[:1000] if result.output else "",
                    summary=result.summary_for_next_agent or "",
                    tokens_used=result.tokens_used,
                    duration_seconds=time.time() - start,
                ).model_dump()
            )
        except Exception as e:
            return json.dumps({"error": str(e), "duration_seconds": time.time() - start})

    async def test_workflow_phase(
        self, phase: str, task: str, previous_output: str | None = None
    ) -> str:
        """Test a specific workflow phase.

        Runs a complete workflow phase (plan, execute, verify, or review)
        with the provided task and optional output from a previous phase.

        Args:
            phase: The workflow phase to test. Must be one of:
                'plan', 'execute', 'verify', 'review'.
            task: The task description for the phase.
            previous_output: Optional output from a previous phase to use
                as context for this phase.

        Returns:
            JSON string containing:
                - phase: Name of the tested phase
                - success: Whether the phase completed successfully
                - output_preview: First 500 chars of the result
                - duration_seconds: Time taken to run

            On error, returns JSON with 'error' and 'duration_seconds' keys.
        """
        from agentfarm.orchestrator import Orchestrator

        start = time.time()
        try:
            orchestrator = Orchestrator(
                provider=None, working_dir=self.working_dir, use_multi_provider=True
            )

            phase_methods = {
                "plan": orchestrator._run_plan_phase,
                "execute": orchestrator._run_execute_phase,
                "verify": orchestrator._run_verify_phase,
                "review": orchestrator._run_review_phase,
            }
            method = phase_methods.get(phase.lower())
            if not method:
                return json.dumps({"error": f"Unknown phase: {phase}"})

            result = await method(task, previous_output)

            return json.dumps(
                {
                    "phase": phase,
                    "success": result.success if hasattr(result, "success") else True,
                    "output_preview": str(result)[:500],
                    "duration_seconds": time.time() - start,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e), "duration_seconds": time.time() - start})

    def run_quick_test(self, component: str | None = None) -> str:
        """Run quick sanity tests on AgentFarm components.

        Executes fast, non-LLM tests to verify that core components
        (imports, agents, tools, memory) are working correctly.

        Args:
            component: Optional specific component to test. If provided,
                must be one of: 'imports', 'agents', 'tools', 'memory'.
                If None, all components are tested.

        Returns:
            JSON string containing:
                - all_passed: Boolean indicating if all tests passed
                - results: Dict mapping component names to their results,
                    where each result has 'passed' (bool) and optionally
                    'error' (str) if the test failed.

            On import error, returns JSON with 'error' key.
        """
        import asyncio
        import inspect

        results = {}

        # Import test functions
        try:
            from evals.quick_test import (
                test_agents,
                test_imports,
                test_memory,
                test_tools,
            )

            tests = {
                "imports": test_imports,
                "agents": test_agents,
                "tools": test_tools,
                "memory": test_memory,
            }
        except ImportError as e:
            return json.dumps({"error": f"Could not import quick_test: {e}"})

        if component and component in tests:
            tests = {component: tests[component]}

        for name, test_func in tests.items():
            try:
                # Handle both sync and async test functions
                if inspect.iscoroutinefunction(test_func):
                    result = asyncio.run(test_func())
                else:
                    result = test_func()
                results[name] = {"passed": bool(result) if result is not None else True}
            except Exception as e:
                results[name] = {"passed": False, "error": str(e)}

        all_passed = all(r["passed"] for r in results.values())
        return json.dumps({"all_passed": all_passed, "results": results})
