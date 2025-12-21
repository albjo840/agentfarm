from __future__ import annotations

"""Long-term memory - persistent storage across sessions."""

import json
import time
from pathlib import Path
from typing import Any

import aiofiles

from agentfarm.memory.base import BaseMemory, MemoryEntry


class LongTermMemory(BaseMemory):
    """Persistent long-term memory using JSON file storage.

    Features:
    - Persists across sessions
    - Async file I/O for non-blocking operations
    - Simple keyword search (can be upgraded to vector search)
    - Organized by project/namespace

    Future improvements:
    - Vector database integration (ChromaDB, Pinecone)
    - Semantic search with embeddings
    - Memory consolidation (summarizing old memories)
    """

    def __init__(
        self,
        storage_path: str | Path = ".agentfarm/memory.json",
        namespace: str = "default",
    ) -> None:
        self.storage_path = Path(storage_path)
        self.namespace = namespace
        self._cache: dict[str, MemoryEntry] = {}
        self._loaded = False

    def _ensure_storage_dir(self) -> None:
        """Ensure storage directory exists."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_sync(self) -> None:
        """Synchronously load memory from disk (for non-async contexts)."""
        if self._loaded:
            return

        self._ensure_storage_dir()

        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    data = json.load(f)
                    ns_data = data.get(self.namespace, {})
                    self._cache = {
                        k: MemoryEntry(**v) for k, v in ns_data.items()
                    }
            except (json.JSONDecodeError, OSError):
                self._cache = {}
        self._loaded = True

    async def _load(self) -> None:
        """Load memory from disk."""
        if self._loaded:
            return

        self._ensure_storage_dir()

        if self.storage_path.exists():
            try:
                async with aiofiles.open(self.storage_path) as f:
                    content = await f.read()
                    data = json.loads(content)
                    ns_data = data.get(self.namespace, {})
                    self._cache = {
                        k: MemoryEntry(**v) for k, v in ns_data.items()
                    }
            except (json.JSONDecodeError, OSError):
                self._cache = {}
        self._loaded = True

    async def _save(self) -> None:
        """Save memory to disk."""
        self._ensure_storage_dir()

        # Load existing data from other namespaces
        existing_data: dict[str, Any] = {}
        if self.storage_path.exists():
            try:
                async with aiofiles.open(self.storage_path) as f:
                    content = await f.read()
                    existing_data = json.loads(content)
            except (json.JSONDecodeError, OSError):
                pass

        # Update our namespace
        existing_data[self.namespace] = {
            k: v.model_dump() for k, v in self._cache.items()
        }

        # Write back
        async with aiofiles.open(self.storage_path, "w") as f:
            await f.write(json.dumps(existing_data, indent=2))

    def _save_sync(self) -> None:
        """Synchronously save memory to disk."""
        self._ensure_storage_dir()

        # Load existing data from other namespaces
        existing_data: dict[str, Any] = {}
        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        # Update our namespace
        existing_data[self.namespace] = {
            k: v.model_dump() for k, v in self._cache.items()
        }

        # Write back
        with open(self.storage_path, "w") as f:
            json.dump(existing_data, f, indent=2)

    def store(
        self,
        key: str,
        value: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a value with immediate persistence."""
        self._load_sync()

        entry = MemoryEntry(
            key=key,
            value=value,
            metadata=metadata or {},
            timestamp=time.time(),
            access_count=0,
        )
        self._cache[key] = entry
        self._save_sync()  # Persist immediately

    async def store_async(
        self,
        key: str,
        value: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a value asynchronously with immediate persistence."""
        await self._load()

        entry = MemoryEntry(
            key=key,
            value=value,
            metadata=metadata or {},
            timestamp=time.time(),
            access_count=0,
        )
        self._cache[key] = entry
        await self._save()

    def retrieve(self, key: str) -> str | None:
        """Retrieve a value."""
        self._load_sync()

        entry = self._cache.get(key)
        if entry:
            entry.access_count += 1
            return entry.value
        return None

    async def retrieve_async(self, key: str) -> str | None:
        """Retrieve a value asynchronously."""
        await self._load()

        entry = self._cache.get(key)
        if entry:
            entry.access_count += 1
            await self._save()  # Persist access count update
            return entry.value
        return None

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Search memory using keyword matching."""
        self._load_sync()

        query_lower = query.lower()
        results: list[tuple[int, MemoryEntry]] = []

        for entry in self._cache.values():
            score = 0
            if query_lower in entry.key.lower():
                score += 10
            if query_lower in entry.value.lower():
                score += 5
            score += entry.access_count

            if score > 0 or not query:
                results.append((score, entry))

        results.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in results[:limit]]

    async def search_async(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Search memory asynchronously."""
        await self._load()
        return self.search(query, limit)

    def clear(self) -> None:
        """Clear all memory in this namespace."""
        self._cache.clear()
        self._loaded = True

    async def clear_async(self) -> None:
        """Clear all memory and persist."""
        self._cache.clear()
        self._loaded = True
        await self._save()

    def list_keys(self) -> list[str]:
        """List all keys in memory."""
        self._load_sync()
        return list(self._cache.keys())

    async def save(self) -> None:
        """Explicitly save to disk."""
        await self._save()

    def __len__(self) -> int:
        self._load_sync()
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        self._load_sync()
        return key in self._cache
