from __future__ import annotations

"""LLM provider implementations - Local-first with Ollama."""

import os
from typing import Any

from agentfarm.providers.base import (
    LLMProvider,
    Message,
    RateLimitError,
    RetryConfig,
    ToolCall,
    ToolResult,
)


def get_provider(
    provider_name: str | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> LLMProvider:
    """Get an LLM provider instance - defaults to local Ollama.

    This project runs all inference locally via Ollama for:
    - Privacy: No data leaves your machine
    - Cost: Completely free
    - Control: You choose the models

    Args:
        provider_name: Provider name (default: "ollama")
        model: Model name (default: from AGENTFARM_MODEL or "qwen2.5-coder:7b")
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured LLMProvider instance (OllamaProvider)

    Examples:
        # Get default Ollama provider
        provider = get_provider()

        # With specific model
        provider = get_provider(model="qwen3:14b")

        # Use the router for automatic model selection
        from agentfarm.providers.router import LLMRouter
        router = LLMRouter()
    """
    # Default to Ollama for local-first operation
    if provider_name is None:
        provider_name = os.environ.get("AGENTFARM_PROVIDER", "ollama")

    return _create_provider(provider_name, model, **kwargs)


def _create_provider(
    provider_name: str,
    model: str | None,
    **kwargs: Any,
) -> LLMProvider:
    """Create a provider instance by name."""
    provider_name = provider_name.lower().replace("-", "_")

    if provider_name == "ollama":
        from agentfarm.providers.ollama import OllamaProvider

        return OllamaProvider(
            model=model or os.environ.get("AGENTFARM_MODEL", "qwen2.5-coder:7b"),
            **kwargs,
        )

    elif provider_name == "router":
        from agentfarm.providers.router import LLMRouter

        # Router handles model selection automatically
        return LLMRouter(**kwargs)

    else:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Supported: ollama, router"
        )


__all__ = [
    "LLMProvider",
    "Message",
    "RateLimitError",
    "RetryConfig",
    "ToolCall",
    "ToolResult",
    "get_provider",
]
