"""
Multi-provider configuration for AgentFarm.

Maps each agent to its optimal LLM provider to maximize free tier usage.
"""

from __future__ import annotations

import os

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentfarm.providers.base import LLMProvider


@dataclass
class AgentProviderConfig:
    """Configuration for an agent's provider."""
    provider_type: str
    model: str
    description: str


# Default agent-to-provider mapping - 100% local GPU
# All agents run on Ollama for maximum reliability (no cloud rate limits)
AGENT_PROVIDER_MAP: dict[str, AgentProviderConfig] = {
    "orchestrator": AgentProviderConfig(
        provider_type="ollama",
        model="llama3.2",
        description="Koordinering - lokal GPU"
    ),
    "planner": AgentProviderConfig(
        provider_type="ollama",
        model="llama3.2",
        description="Planering - lokal GPU"
    ),
    "executor": AgentProviderConfig(
        provider_type="ollama",
        model="codellama",  # Specialiserad för kod!
        description="Kod-generering - lokal kodmodell"
    ),
    "verifier": AgentProviderConfig(
        provider_type="ollama",
        model="llama3.2",
        description="Verifiering - lokal GPU"
    ),
    "designer": AgentProviderConfig(
        provider_type="ollama",
        model="llama3.2",
        description="UI/UX design - lokal GPU"
    ),
    "reviewer": AgentProviderConfig(
        provider_type="ollama",
        model="llama3.2",
        description="Kod-review - lokal GPU"
    ),
}


def get_available_provider_for_agent(agent_name: str) -> AgentProviderConfig:
    """Get the best available provider for an agent.

    Falls back to other providers if the preferred one isn't available.
    """
    config = AGENT_PROVIDER_MAP.get(agent_name.lower())
    if not config:
        # Default fallback
        config = AGENT_PROVIDER_MAP["orchestrator"]

    # Check if the provider is available
    if not _is_provider_available(config.provider_type):
        # Try fallbacks in order of preference (ollama first since it's always available locally)
        fallback_order = ["ollama", "groq", "gemini", "qwen"]
        for fallback in fallback_order:
            if _is_provider_available(fallback):
                # Get a model for this fallback provider
                return AgentProviderConfig(
                    provider_type=fallback,
                    model=_get_default_model(fallback),
                    description=f"Fallback from {config.provider_type}"
                )

    return config


def _is_provider_available(provider_type: str) -> bool:
    """Check if a provider is available based on API keys."""
    if provider_type == "groq":
        return bool(os.getenv("GROQ_API_KEY"))
    elif provider_type == "gemini":
        return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    elif provider_type == "qwen":
        return bool(os.getenv("SILICONFLOW_API_KEY"))
    elif provider_type == "ollama":
        # Ollama is always potentially available (local)
        return True
    elif provider_type == "claude":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    return False


def _get_default_model(provider_type: str) -> str:
    """Get default model for a provider."""
    defaults = {
        "groq": "llama-3.3-70b-versatile",
        "gemini": "gemini-1.5-flash",
        "qwen": "Qwen/Qwen2.5-7B-Instruct",
        "ollama": "llama3.2",
        "claude": "claude-sonnet-4-20250514",
    }
    return defaults.get(provider_type, "llama-3.3-70b-versatile")


def create_provider_for_agent(agent_name: str) -> "LLMProvider":
    """Create an LLM provider instance for a specific agent."""
    config = get_available_provider_for_agent(agent_name)
    return _create_provider(config.provider_type, config.model)


def _create_provider(provider_type: str, model: str) -> "LLMProvider":
    """Create a provider instance."""
    if provider_type == "groq":
        from agentfarm.providers.groq import GroqProvider
        return GroqProvider(
            model=model,
            api_key=os.getenv("GROQ_API_KEY"),
        )

    elif provider_type == "gemini":
        from agentfarm.providers.gemini import GeminiProvider
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        return GeminiProvider(
            model=model,
            api_key=api_key,
        )

    elif provider_type == "qwen":
        from agentfarm.providers.siliconflow import SiliconFlowProvider
        return SiliconFlowProvider(
            model=model,
            api_key=os.getenv("SILICONFLOW_API_KEY"),
        )

    elif provider_type == "ollama":
        from agentfarm.providers.ollama import OllamaProvider
        return OllamaProvider(
            model=model,
            base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        )

    elif provider_type == "claude":
        from agentfarm.providers.claude import ClaudeProvider
        return ClaudeProvider(
            model=model,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )

    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


def get_provider_status() -> dict[str, dict]:
    """Get status of all providers and their agent assignments."""
    status = {}

    for agent_name, config in AGENT_PROVIDER_MAP.items():
        available = _is_provider_available(config.provider_type)
        actual_config = get_available_provider_for_agent(agent_name)

        status[agent_name] = {
            "preferred_provider": config.provider_type,
            "preferred_model": config.model,
            "actual_provider": actual_config.provider_type,
            "actual_model": actual_config.model,
            "available": available,
            "using_fallback": actual_config.provider_type != config.provider_type,
            "description": config.description,
        }

    return status


def print_provider_status():
    """Print a nice summary of provider status."""
    status = get_provider_status()

    print("\n" + "=" * 60)
    print("  AGENTFARM MULTI-PROVIDER STATUS")
    print("=" * 60)

    for agent, info in status.items():
        icon = "✓" if info["available"] else "✗"
        fallback = " (FALLBACK)" if info["using_fallback"] else ""
        print(f"\n  {agent.upper()}")
        print(f"    {icon} {info['actual_provider'].upper()}{fallback}")
        print(f"      Model: {info['actual_model']}")
        print(f"      {info['description']}")

    print("\n" + "=" * 60)
