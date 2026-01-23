"""Prompt tool handler for MCP introspection of agent prompts.

This module provides tools for viewing, testing, and customizing agent system prompts
via the Model Context Protocol.
"""

from __future__ import annotations

import json
import importlib

from .schemas import PromptInfo


class PromptToolHandler:
    """Handler for prompt-related MCP tools.

    Provides functionality to inspect, list, test, and customize agent system prompts.
    This enables runtime introspection and modification of agent behavior through
    their system prompts.

    Attributes:
        working_dir: The working directory for agent operations.
    """

    def __init__(self, working_dir: str):
        """Initialize the PromptToolHandler.

        Args:
            working_dir: The working directory path for agent operations.
        """
        self.working_dir = working_dir

    def _get_agent_class(self, agent: str):
        """Get the agent class by name.

        Maps agent names to their fully qualified class paths and dynamically
        imports the corresponding class.

        Args:
            agent: The agent name (e.g., 'planner', 'executor', 'verifier').

        Returns:
            The agent class if found, None otherwise.
        """
        agent_map = {
            "planner": "agentfarm.agents.planner.PlannerAgent",
            "executor": "agentfarm.agents.executor.ExecutorAgent",
            "verifier": "agentfarm.agents.verifier.VerifierAgent",
            "reviewer": "agentfarm.agents.reviewer.ReviewerAgent",
            "ux_designer": "agentfarm.agents.ux_designer.UXDesignerAgent",
            "orchestrator": "agentfarm.agents.orchestrator_agent.OrchestratorAgent",
        }
        path = agent_map.get(agent.lower())
        if not path:
            return None
        module_path, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    def get_prompt(self, agent: str) -> str:
        """Get the system prompt for a specific agent.

        Instantiates the agent class with a None provider to access its
        system_prompt property and returns detailed information about it.

        Args:
            agent: The agent name (e.g., 'planner', 'executor').

        Returns:
            JSON string containing PromptInfo with agent name, prompt text,
            length, and whether a custom suffix is configured. Returns an
            error JSON if the agent is unknown or cannot be loaded.
        """
        cls = self._get_agent_class(agent)
        if not cls:
            return json.dumps({"error": f"Unknown agent: {agent}"})
        try:
            instance = cls(provider=None)
            return json.dumps(PromptInfo(
                agent=agent,
                prompt=instance.system_prompt,
                length=len(instance.system_prompt),
                has_custom_suffix=bool(getattr(instance, '_custom_prompt_suffix', None)),
            ).model_dump())
        except Exception as e:
            return json.dumps({"error": str(e)})

    def list_prompts(self) -> str:
        """List all available agent prompts with previews.

        Iterates through all known agents and returns summary information
        about each agent's system prompt including a preview of the first
        200 characters.

        Returns:
            JSON string containing a list of prompt summaries with agent name,
            prompt length, and preview text. Includes a count of total prompts.
        """
        agents = ["planner", "executor", "verifier", "reviewer", "ux_designer", "orchestrator"]
        prompts = []
        for agent in agents:
            cls = self._get_agent_class(agent)
            if cls:
                try:
                    instance = cls(provider=None)
                    prompts.append({
                        "agent": agent,
                        "length": len(instance.system_prompt),
                        "preview": instance.system_prompt[:200] + "...",
                    })
                except Exception:
                    prompts.append({"agent": agent, "error": "Could not load"})
        return json.dumps({"prompts": prompts, "count": len(prompts)})

    async def test_prompt(self, agent: str, test_input: str, custom_suffix: str | None = None) -> str:
        """Test an agent's prompt with a sample input.

        Creates an agent instance with an Ollama provider and runs it with
        the provided test input. Optionally applies a custom prompt suffix
        before running.

        Args:
            agent: The agent name to test.
            test_input: The test task/input to send to the agent.
            custom_suffix: Optional custom text to append to the system prompt.

        Returns:
            JSON string containing test results including success status,
            output preview (first 500 chars), summary for next agent, and
            whether a custom suffix was used. Returns error JSON on failure.
        """
        from agentfarm.providers.ollama import OllamaProvider
        from agentfarm.agents.base import AgentContext

        cls = self._get_agent_class(agent)
        if not cls:
            return json.dumps({"error": f"Unknown agent: {agent}"})

        try:
            provider = OllamaProvider()
            instance = cls(provider=provider)
            if custom_suffix:
                instance.set_custom_prompt(custom_suffix)

            context = AgentContext(task_summary=test_input, working_dir=self.working_dir)
            result = await instance.run(context)

            return json.dumps({
                "agent": agent,
                "success": result.success,
                "output_preview": result.output[:500] if result.output else "",
                "summary": result.summary_for_next_agent,
                "custom_suffix_used": bool(custom_suffix),
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    def set_custom_prompt(self, agent: str, custom_text: str) -> str:
        """Configure a custom prompt suffix for an agent.

        This method validates the agent name and returns configuration status.
        Note that the actual custom prompt must be applied when instantiating
        the agent via the agent's set_custom_prompt method.

        Args:
            agent: The agent name to configure.
            custom_text: The custom text to append to the agent's system prompt.

        Returns:
            JSON string with agent name, custom text, and status indicating
            the configuration is ready. Returns error JSON if agent is unknown.
        """
        cls = self._get_agent_class(agent)
        if not cls:
            return json.dumps({"error": f"Unknown agent: {agent}"})
        return json.dumps({"agent": agent, "custom_text": custom_text, "status": "configured"})
