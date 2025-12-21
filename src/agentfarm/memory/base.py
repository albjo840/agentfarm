from __future__ import annotations

"""Base classes for agent memory system."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """A single memory entry."""

    key: str
    value: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = 0.0
    access_count: int = 0


class BaseMemory(ABC):
    """Abstract base class for memory implementations."""

    @abstractmethod
    def store(self, key: str, value: str, metadata: dict[str, Any] | None = None) -> None:
        """Store a value in memory."""

    @abstractmethod
    def retrieve(self, key: str) -> str | None:
        """Retrieve a value from memory."""

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Search memory for relevant entries."""

    @abstractmethod
    def clear(self) -> None:
        """Clear all memory."""

    @abstractmethod
    def list_keys(self) -> list[str]:
        """List all keys in memory."""


class MemoryManager:
    """Manages both short-term and long-term memory for an agent.

    Short-term memory: Session-scoped, fast, limited capacity
    Long-term memory: Persistent, larger capacity, may use disk/DB
    """

    def __init__(
        self,
        short_term: BaseMemory,
        long_term: BaseMemory,
    ) -> None:
        self.short_term = short_term
        self.long_term = long_term

    def store(
        self,
        key: str,
        value: str,
        long_term: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store value in appropriate memory."""
        if long_term:
            self.long_term.store(key, value, metadata)
        else:
            self.short_term.store(key, value, metadata)

    def retrieve(self, key: str, search_both: bool = True) -> str | None:
        """Retrieve value, optionally searching both memories."""
        # Check short-term first
        value = self.short_term.retrieve(key)
        if value:
            return value

        # Fall back to long-term if allowed
        if search_both:
            return self.long_term.retrieve(key)

        return None

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Search both memories for relevant entries."""
        short_results = self.short_term.search(query, limit)
        long_results = self.long_term.search(query, limit)

        # Combine and sort by relevance (access_count as proxy)
        combined = short_results + long_results
        combined.sort(key=lambda x: x.access_count, reverse=True)
        return combined[:limit]

    def promote_to_long_term(self, key: str) -> bool:
        """Promote a short-term memory to long-term."""
        value = self.short_term.retrieve(key)
        if value:
            self.long_term.store(key, value)
            return True
        return False

    def clear_short_term(self) -> None:
        """Clear short-term memory (e.g., at session end)."""
        self.short_term.clear()

    def get_context_summary(self, max_entries: int = 10) -> str:
        """Get a summary of recent memory for context injection."""
        entries = self.short_term.search("", limit=max_entries)
        if not entries:
            return ""

        lines = ["Recent context:"]
        for entry in entries:
            lines.append(f"  - {entry.key}: {entry.value[:100]}...")
        return "\n".join(lines)
