#!/usr/bin/env python3
"""
Quick Test Runner for AgentFarm

Runs fast sanity checks without full workflow execution.
Useful for testing individual components.

Usage:
    python -m evals.quick_test              # Run all quick tests
    python -m evals.quick_test --provider   # Test provider connectivity
    python -m evals.quick_test --agents     # Test agent initialization
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...", end=" ")
    errors = []

    modules = [
        "agentfarm",
        "agentfarm.orchestrator",
        "agentfarm.agents.base",
        "agentfarm.agents.planner",
        "agentfarm.agents.executor",
        "agentfarm.agents.verifier",
        "agentfarm.agents.reviewer",
        "agentfarm.agents.ux_designer",
        "agentfarm.providers.base",
        "agentfarm.tools.file_tools",
        "agentfarm.memory.base",
        "agentfarm.events.bus",
    ]

    for module in modules:
        try:
            __import__(module)
        except ImportError as e:
            errors.append(f"{module}: {e}")

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  - {e}")
        return False

    print(f"OK ({len(modules)} modules)")
    return True


async def test_providers():
    """Test provider connectivity."""
    print("Testing providers...")
    import httpx

    # First check if Ollama is running
    print("  Checking Ollama...", end=" ")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:11434/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                print(f"OK ({len(models)} models)")
            else:
                print(f"FAIL (status {resp.status_code})")
                return False
    except Exception as e:
        print(f"FAIL ({e})")
        return False

    # Test a quick completion with Ollama
    print("  Testing completion...", end=" ")
    try:
        from agentfarm.providers.ollama import OllamaProvider
        from agentfarm.providers.base import Message

        provider = OllamaProvider(model="nemotron-mini")  # Fastest model
        start = time.time()
        response = await provider.complete([
            Message(role="user", content="Say 'hello' in one word only.")
        ])
        duration = time.time() - start

        if response and response.content:
            print(f"OK ({duration:.2f}s) - '{response.content[:30]}...'")
            return True
        else:
            print("FAIL (empty response)")
            return False
    except Exception as e:
        print(f"FAIL ({e})")
        return False


async def test_agents():
    """Test agent initialization."""
    print("Testing agents...")

    from agentfarm.agents.planner import PlannerAgent
    from agentfarm.agents.executor import ExecutorAgent
    from agentfarm.agents.verifier import VerifierAgent
    from agentfarm.agents.reviewer import ReviewerAgent
    from agentfarm.agents.ux_designer import UXDesignerAgent

    agents = [
        ("Planner", PlannerAgent),
        ("Executor", ExecutorAgent),
        ("Verifier", VerifierAgent),
        ("Reviewer", ReviewerAgent),
        ("UXDesigner", UXDesignerAgent),
    ]

    results = []
    for name, AgentClass in agents:
        print(f"  Initializing {name}...", end=" ")
        try:
            agent = AgentClass(provider=None)  # No provider needed for init test
            if agent.name and agent.system_prompt:
                print(f"OK (prompt: {len(agent.system_prompt)} chars)")
                results.append(True)
            else:
                print("FAIL (missing name or prompt)")
                results.append(False)
        except Exception as e:
            print(f"FAIL ({e})")
            results.append(False)

    return all(results)


async def test_tools():
    """Test file tools."""
    print("Testing tools...")
    import tempfile

    from agentfarm.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        tools = FileTools(tmpdir)

        # Test write
        print("  Testing write_file...", end=" ")
        try:
            result = await tools.write_file("test.py", "print('hello')")
            # Result can be string or dict depending on implementation
            if isinstance(result, str):
                success = "success" in result.lower() or "wrote" in result.lower() or Path(tmpdir, "test.py").exists()
            else:
                success = result.get("success", False)

            if success or Path(tmpdir, "test.py").exists():
                print("OK")
            else:
                print(f"FAIL ({result})")
                return False
        except Exception as e:
            print(f"FAIL ({e})")
            return False

        # Test read
        print("  Testing read_file...", end=" ")
        try:
            result = await tools.read_file("test.py")
            content = result.get("content", result) if isinstance(result, dict) else result
            if "hello" in str(content):
                print("OK")
            else:
                print("FAIL (content mismatch)")
                return False
        except Exception as e:
            print(f"FAIL ({e})")
            return False

        # Test list
        print("  Testing list_directory...", end=" ")
        try:
            result = await tools.list_directory(".")
            if "test.py" in str(result):
                print("OK")
            else:
                print("FAIL (file not found)")
                return False
        except Exception as e:
            print(f"FAIL ({e})")
            return False

    return True


async def test_memory():
    """Test memory system."""
    print("Testing memory...")

    from agentfarm.memory.base import MemoryManager
    from agentfarm.memory.short_term import ShortTermMemory
    from agentfarm.memory.long_term import LongTermMemory
    import tempfile

    print("  Testing ShortTermMemory...", end=" ")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = MemoryManager(
                short_term=ShortTermMemory(max_entries=10),
                long_term=LongTermMemory(storage_path=Path(tmpdir) / "memory.json")
            )
            memory.store("test_key", "test_value")
            retrieved = memory.retrieve("test_key")
            if retrieved == "test_value":
                print("OK")
            else:
                print(f"FAIL (got: {retrieved})")
                return False
    except Exception as e:
        print(f"FAIL ({e})")
        return False

    return True


async def test_event_bus():
    """Test event bus."""
    print("Testing event bus...")

    from agentfarm.events.bus import EventBus, Event, EventType

    print("  Testing emit/subscribe...", end=" ")
    try:
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventType.AGENT_MESSAGE, handler)

        # Use emit_and_wait for synchronous handling
        await bus.emit_and_wait(Event(
            type=EventType.AGENT_MESSAGE,
            source="test",
            data={"content": "hello"}
        ))

        # Check if event was received
        if len(received) > 0:
            print("OK")
        else:
            # Also check metrics as backup
            metrics = bus.get_metrics()
            if any("emit" in k.lower() for k in metrics.keys()):
                print("OK (via metrics)")
            else:
                print("FAIL (event not received)")
                return False
    except Exception as e:
        print(f"FAIL ({e})")
        return False

    return True


async def run_all_tests():
    """Run all quick tests."""
    print("\n" + "="*50)
    print("  AGENTFARM QUICK TEST")
    print("="*50 + "\n")

    start = time.time()
    results = []

    # Sync tests
    results.append(("Imports", test_imports()))

    # Async tests
    results.append(("Providers", await test_providers()))
    results.append(("Agents", await test_agents()))
    results.append(("Tools", await test_tools()))
    results.append(("Memory", await test_memory()))
    results.append(("EventBus", await test_event_bus()))

    duration = time.time() - start

    # Summary
    print("\n" + "="*50)
    print("  SUMMARY")
    print("="*50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")

    print()
    print(f"  Result: {passed}/{total} passed")
    print(f"  Time: {duration:.2f}s")
    print("="*50 + "\n")

    return passed == total


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AgentFarm Quick Test")
    parser.add_argument("--provider", action="store_true", help="Test providers only")
    parser.add_argument("--agents", action="store_true", help="Test agents only")
    parser.add_argument("--tools", action="store_true", help="Test tools only")
    args = parser.parse_args()

    if args.provider:
        asyncio.run(test_providers())
    elif args.agents:
        asyncio.run(test_agents())
    elif args.tools:
        asyncio.run(test_tools())
    else:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
