"""Tests for the memory system."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agentfarm.memory.base import MemoryEntry, MemoryManager
from agentfarm.memory.long_term import LongTermMemory
from agentfarm.memory.short_term import ShortTermMemory


class TestMemoryEntry:
    """Tests for MemoryEntry model."""

    def test_create_entry(self) -> None:
        entry = MemoryEntry(
            key="test_key",
            value="test_value",
            timestamp=1234567890.0,
            access_count=5,
        )
        assert entry.key == "test_key"
        assert entry.value == "test_value"
        assert entry.timestamp == 1234567890.0
        assert entry.access_count == 5

    def test_entry_with_metadata(self) -> None:
        entry = MemoryEntry(
            key="test",
            value="data",
            metadata={"source": "user", "importance": "high"},
        )
        assert entry.metadata["source"] == "user"
        assert entry.metadata["importance"] == "high"


class TestShortTermMemory:
    """Tests for ShortTermMemory."""

    def test_store_and_retrieve(self) -> None:
        memory = ShortTermMemory()
        memory.store("key1", "value1")
        assert memory.retrieve("key1") == "value1"

    def test_retrieve_nonexistent(self) -> None:
        memory = ShortTermMemory()
        assert memory.retrieve("nonexistent") is None

    def test_lru_eviction(self) -> None:
        memory = ShortTermMemory(max_entries=3)
        memory.store("key1", "value1")
        memory.store("key2", "value2")
        memory.store("key3", "value3")
        memory.store("key4", "value4")  # Should evict key1

        assert memory.retrieve("key1") is None
        assert memory.retrieve("key2") == "value2"
        assert memory.retrieve("key4") == "value4"

    def test_access_updates_order(self) -> None:
        memory = ShortTermMemory(max_entries=3)
        memory.store("key1", "value1")
        memory.store("key2", "value2")
        memory.store("key3", "value3")

        # Access key1 to make it recently used
        memory.retrieve("key1")

        # Add new key - should evict key2 (least recently used)
        memory.store("key4", "value4")

        assert memory.retrieve("key1") == "value1"  # Still there
        assert memory.retrieve("key2") is None  # Evicted
        assert memory.retrieve("key4") == "value4"

    def test_search_by_key(self) -> None:
        memory = ShortTermMemory()
        memory.store("user_name", "Alice")
        memory.store("user_email", "alice@example.com")
        memory.store("project_name", "AgentFarm")

        results = memory.search("user")
        assert len(results) == 2
        keys = {r.key for r in results}
        assert "user_name" in keys
        assert "user_email" in keys

    def test_search_by_value(self) -> None:
        memory = ShortTermMemory()
        memory.store("greeting", "Hello world")
        memory.store("farewell", "Goodbye world")
        memory.store("question", "How are you?")

        results = memory.search("world")
        assert len(results) == 2

    def test_clear(self) -> None:
        memory = ShortTermMemory()
        memory.store("key1", "value1")
        memory.store("key2", "value2")
        memory.clear()

        assert memory.retrieve("key1") is None
        assert len(memory) == 0

    def test_list_keys(self) -> None:
        memory = ShortTermMemory()
        memory.store("key1", "value1")
        memory.store("key2", "value2")

        keys = memory.list_keys()
        assert set(keys) == {"key1", "key2"}

    def test_contains(self) -> None:
        memory = ShortTermMemory()
        memory.store("key1", "value1")

        assert "key1" in memory
        assert "key2" not in memory


class TestLongTermMemory:
    """Tests for LongTermMemory."""

    def test_store_and_retrieve(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"
            memory = LongTermMemory(storage_path=storage_path)

            memory.store("key1", "value1")
            assert memory.retrieve("key1") == "value1"

    def test_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"

            # Store in first instance
            memory1 = LongTermMemory(storage_path=storage_path)
            memory1.store("persistent_key", "persistent_value")

            # Create new instance - should load from disk
            memory2 = LongTermMemory(storage_path=storage_path)
            assert memory2.retrieve("persistent_key") == "persistent_value"

    def test_namespace_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"

            memory_ns1 = LongTermMemory(storage_path=storage_path, namespace="project1")
            memory_ns2 = LongTermMemory(storage_path=storage_path, namespace="project2")

            memory_ns1.store("key", "value_from_project1")
            memory_ns2.store("key", "value_from_project2")

            assert memory_ns1.retrieve("key") == "value_from_project1"
            assert memory_ns2.retrieve("key") == "value_from_project2"

    def test_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"
            memory = LongTermMemory(storage_path=storage_path)

            memory.store("api_endpoint", "https://api.example.com")
            memory.store("api_key", "secret123")
            memory.store("database_url", "postgres://localhost")

            results = memory.search("api")
            assert len(results) == 2

    def test_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"
            memory = LongTermMemory(storage_path=storage_path)

            memory.store("key1", "value1")
            memory.clear()

            assert memory.retrieve("key1") is None
            assert len(memory) == 0


class TestMemoryManager:
    """Tests for MemoryManager."""

    def test_store_and_retrieve_short_term(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"
            manager = MemoryManager(
                short_term=ShortTermMemory(),
                long_term=LongTermMemory(storage_path=storage_path),
            )

            manager.store("key", "value", long_term=False)
            assert manager.retrieve("key") == "value"

    def test_store_and_retrieve_long_term(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"
            manager = MemoryManager(
                short_term=ShortTermMemory(),
                long_term=LongTermMemory(storage_path=storage_path),
            )

            manager.store("key", "value", long_term=True)
            assert manager.retrieve("key") == "value"

    def test_search_both_memories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"
            manager = MemoryManager(
                short_term=ShortTermMemory(),
                long_term=LongTermMemory(storage_path=storage_path),
            )

            manager.store("short_config", "short_value", long_term=False)
            manager.store("long_config", "long_value", long_term=True)

            results = manager.search("config")
            assert len(results) == 2

    def test_promote_to_long_term(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"
            manager = MemoryManager(
                short_term=ShortTermMemory(),
                long_term=LongTermMemory(storage_path=storage_path),
            )

            manager.store("important_key", "important_value", long_term=False)
            success = manager.promote_to_long_term("important_key")

            assert success
            assert manager.long_term.retrieve("important_key") == "important_value"

    def test_clear_short_term(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"
            manager = MemoryManager(
                short_term=ShortTermMemory(),
                long_term=LongTermMemory(storage_path=storage_path),
            )

            manager.store("short_key", "short_value", long_term=False)
            manager.store("long_key", "long_value", long_term=True)

            manager.clear_short_term()

            assert manager.short_term.retrieve("short_key") is None
            assert manager.long_term.retrieve("long_key") == "long_value"

    def test_get_context_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "memory.json"
            manager = MemoryManager(
                short_term=ShortTermMemory(),
                long_term=LongTermMemory(storage_path=storage_path),
            )

            manager.store("task", "Implement feature X", long_term=False)
            manager.store("decision", "Use async/await pattern", long_term=False)

            summary = manager.get_context_summary()
            assert "Recent context:" in summary
            assert "task" in summary or "decision" in summary
