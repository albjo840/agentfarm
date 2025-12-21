from __future__ import annotations

"""LLM provider implementations."""

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
    """Get an LLM provider instance, with auto-detection if no provider specified.

    Provider selection priority (when provider_name is None):
    1. AGENTFARM_PROVIDER environment variable
    2. GROQ_API_KEY present -> GroqProvider
    3. ANTHROPIC_API_KEY present -> ClaudeProvider
    4. AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT present -> AzureOpenAIProvider
    5. OLLAMA_HOST or localhost Ollama -> OllamaProvider

    Args:
        provider_name: Explicit provider name ("groq", "claude", "azure_openai", "ollama")
        model: Model name (optional, uses provider defaults)
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured LLMProvider instance

    Raises:
        ValueError: If no provider can be determined or configured

    Examples:
        # Auto-detect provider from environment
        provider = get_provider()

        # Explicit provider with custom model
        provider = get_provider("claude", model="claude-opus-4-5-20251101")

        # With retry configuration
        provider = get_provider("groq", retry_config=RetryConfig(max_retries=5))
    """
    # Check for explicit provider name
    if provider_name is None:
        provider_name = os.environ.get("AGENTFARM_PROVIDER")

    # Auto-detect based on available credentials
    if provider_name is None:
        provider_name = _detect_provider()

    if provider_name is None:
        raise ValueError(
            "No LLM provider could be detected. Please set one of:\n"
            "- GROQ_API_KEY (recommended, fast & free)\n"
            "- GOOGLE_API_KEY or GEMINI_API_KEY (Gemini, generous free tier)\n"
            "- SILICONFLOW_API_KEY (Qwen models, free tier)\n"
            "- ANTHROPIC_API_KEY (Claude)\n"
            "- AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT\n"
            "- OLLAMA_HOST for local inference\n"
            "\nOr set AGENTFARM_PROVIDER explicitly."
        )

    return _create_provider(provider_name, model, **kwargs)


def _detect_provider() -> str | None:
    """Detect available provider from environment variables."""
    # Priority 1: Groq (fast, free tier)
    if os.environ.get("GROQ_API_KEY"):
        return "groq"

    # Priority 2: Gemini (Google, generous free tier)
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return "gemini"

    # Priority 3: SiliconFlow/Qwen (free tier for Qwen models)
    if os.environ.get("SILICONFLOW_API_KEY"):
        return "siliconflow"

    # Priority 4: Claude (high quality)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"

    # Priority 5: Azure OpenAI (enterprise)
    if os.environ.get("AZURE_OPENAI_API_KEY") and os.environ.get("AZURE_OPENAI_ENDPOINT"):
        return "azure_openai"

    # Priority 6: Ollama (local, free)
    if os.environ.get("OLLAMA_HOST"):
        return "ollama"

    return None


def _create_provider(
    provider_name: str,
    model: str | None,
    **kwargs: Any,
) -> LLMProvider:
    """Create a provider instance by name."""
    provider_name = provider_name.lower().replace("-", "_")

    if provider_name == "groq":
        from agentfarm.providers.groq import GroqProvider

        return GroqProvider(
            model=model or os.environ.get("AGENTFARM_MODEL", "llama-3.3-70b-versatile"),
            **kwargs,
        )

    elif provider_name == "claude" or provider_name == "anthropic":
        from agentfarm.providers.claude import ClaudeProvider

        return ClaudeProvider(
            model=model or os.environ.get("AGENTFARM_MODEL", "claude-sonnet-4-20250514"),
            **kwargs,
        )

    elif provider_name == "azure_openai" or provider_name == "azure":
        from agentfarm.providers.azure import AzureOpenAIProvider

        return AzureOpenAIProvider(
            model=model or os.environ.get("AGENTFARM_MODEL"),
            **kwargs,
        )

    elif provider_name == "ollama":
        from agentfarm.providers.ollama import OllamaProvider

        return OllamaProvider(
            model=model or os.environ.get("AGENTFARM_MODEL", "llama3.2"),
            **kwargs,
        )

    elif provider_name == "gemini" or provider_name == "google":
        from agentfarm.providers.gemini import GeminiProvider

        return GeminiProvider(
            model=model or os.environ.get("AGENTFARM_MODEL", "gemini-1.5-flash-latest"),
            **kwargs,
        )

    elif provider_name in ("siliconflow", "qwen"):
        from agentfarm.providers.siliconflow import SiliconFlowProvider

        return SiliconFlowProvider(
            model=model or os.environ.get("AGENTFARM_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
            **kwargs,
        )

    else:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Supported: groq, gemini, siliconflow, qwen, claude, azure_openai, ollama"
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
