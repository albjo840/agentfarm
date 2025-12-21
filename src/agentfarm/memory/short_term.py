from __future__ import annotations

"""Short-term memory - session-scoped, fast, in-memory storage."""

import time
from collections import OrderedDict
from typing import Any

from agentfarm.memory.base import BaseMemory, MemoryEntry


class ShortTermMemory(BaseMemory):
    """In-memory short-term storage with LRU eviction.

    Features:
    - Fast in-memory storage
    - LRU eviction when capacity is reached
    - Session-scoped (cleared between sessions)
    - Simple keyword search
    """

    def __init__(self, max_entries: int = 100) -> None:
        self.max_entries = max_entries
        self._storage: OrderedDict[str, MemoryEntry] = OrderedDict()

    def store(
        self,
        key: str,
        value: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a value, evicting oldest if at capacity."""
        # Remove oldest entries if at capacity
        while len(self._storage) >= self.max_entries:
            self._storage.popitem(last=False)

        entry = MemoryEntry(
            key=key,
            value=value,
            metadata=metadata or {},
            timestamp=time.time(),
            access_count=0,
        )
        self._storage[key] = entry

    def retrieve(self, key: str) -> str | None:
        """Retrieve a value and update access count."""
        entry = self._storage.get(key)
        if entry:
            entry.access_count += 1
            # Move to end (most recently accessed)
            self._storage.move_to_end(key)
            return entry.value
        return None

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Search memory using simple keyword matching."""
        query_lower = query.lower()
        results: list[tuple[int, MemoryEntry]] = []

        for entry in self._storage.values():
            score = 0
            # Score based on key match
            if query_lower in entry.key.lower():
                score += 10
            # Score based on value match
            if query_lower in entry.value.lower():
                score += 5
            # Boost by access count
            score += entry.access_count

            if score > 0 or not query:  # Include all if empty query
                results.append((score, entry))

        # Sort by score descending
        results.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in results[:limit]]

    def clear(self) -> None:
        """Clear all memory."""
        self._storage.clear()

    def list_keys(self) -> list[str]:
        """List all keys in memory."""
        return list(self._storage.keys())

    def get_recent(self, n: int = 10) -> list[MemoryEntry]:
        """Get the n most recently accessed entries."""
        entries = list(self._storage.values())
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        return entries[:n]

    def __len__(self) -> int:
        return len(self._storage)

    def __contains__(self, key: str) -> bool:
        return key in self._storage
