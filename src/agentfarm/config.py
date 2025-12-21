from __future__ import annotations

"""Configuration for AgentFarm."""

import os
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ProviderType(str, Enum):
    """Available LLM providers."""

    OLLAMA = "ollama"
    GROQ = "groq"
    GEMINI = "gemini"
    SILICONFLOW = "siliconflow"
    QWEN = "qwen"  # Alias for siliconflow
    CLAUDE = "claude"
    AZURE_OPENAI = "azure_openai"
    AZURE_ML = "azure_ml"


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""

    type: ProviderType = ProviderType.GROQ
    model: str = "llama-3.3-70b-versatile"
    base_url: str | None = None
    api_key: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SandboxConfig(BaseModel):
    """Configuration for Docker sandbox."""

    enabled: bool = True
    image: str = "python:3.11-slim"
    timeout: int = 30
    memory: str = "256m"
    cpu_limit: float = 0.5


class AgentFarmConfig(BaseModel):
    """Main configuration for AgentFarm."""

    working_dir: str = "."
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)

    # Token efficiency settings
    max_context_tokens: int = 4000
    summarize_threshold: int = 2000

    @classmethod
    def from_env(cls) -> "AgentFarmConfig":
        """Load configuration from environment variables."""
        provider_type = os.getenv("AGENTFARM_PROVIDER", "groq")
        model = os.getenv("AGENTFARM_MODEL")

        # Provider-specific API keys and defaults
        api_key = os.getenv("AGENTFARM_API_KEY")
        base_url = None

        if provider_type == "ollama":
            base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            model = model or "llama3.2"
        elif provider_type == "groq":
            api_key = api_key or os.getenv("GROQ_API_KEY")
            base_url = os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1")
            model = model or "llama-3.3-70b-versatile"
        elif provider_type == "gemini":
            api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            model = model or "gemini-1.5-flash-latest"
        elif provider_type in ("siliconflow", "qwen"):
            api_key = api_key or os.getenv("SILICONFLOW_API_KEY")
            model = model or "Qwen/Qwen2.5-7B-Instruct"
        elif provider_type == "claude":
            api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            model = model or "claude-sonnet-4-20250514"
        elif provider_type == "azure_openai":
            api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
            base_url = os.getenv("AZURE_OPENAI_ENDPOINT")
            model = model or "gpt-4"

        return cls(
            working_dir=os.getenv("AGENTFARM_WORKDIR", "."),
            provider=ProviderConfig(
                type=ProviderType(provider_type),
                model=model or "llama-3.3-70b-versatile",
                base_url=base_url,
                api_key=api_key,
            ),
            sandbox=SandboxConfig(
                enabled=os.getenv("AGENTFARM_SANDBOX", "true").lower() == "true",
            ),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "AgentFarmConfig":
        """Load configuration from a JSON/YAML file."""
        import json

        path = Path(path)
        if not path.exists():
            return cls()

        with open(path) as f:
            data = json.load(f)

        return cls(**data)


def get_default_config() -> AgentFarmConfig:
    """Get default configuration, checking env vars first."""
    # Check for config file
    config_paths = [
        Path("agentfarm.json"),
        Path(".agentfarm.json"),
        Path.home() / ".config" / "agentfarm" / "config.json",
    ]

    for path in config_paths:
        if path.exists():
            return AgentFarmConfig.from_file(path)

    # Fall back to environment variables
    return AgentFarmConfig.from_env()
