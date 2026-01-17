"""
AgentFarm Agent Chain Evaluation Tests

Tests agent chain performance including:
- Agent collaboration
- Failure recovery
- Parallel execution
- Multi-agent coordination

Usage:
    python -m evals.agent_chain_tests                  # Run all tests
    python -m evals.agent_chain_tests --category collab # Run collaboration tests
    python -m evals.agent_chain_tests --quick          # Run quick validation
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from evals.suite import (
    TestCase, TestResult, EvalReport, VALIDATORS,
    validate_file_exists, validate_python_syntax, validate_function_exists,
    CATEGORY_CODEGEN, CATEGORY_MULTISTEP
)

# New categories for agent chain tests
CATEGORY_COLLABORATION = "collaboration"
CATEGORY_RECOVERY = "recovery"
CATEGORY_PARALLEL = "parallel"
CATEGORY_CHAIN = "chain"


# ===========================================
# Additional Validators for Agent Chain
# ===========================================

def validate_multiple_files_exist(project_path: Path, files: list[str]) -> tuple[bool, str]:
    """Check if multiple files exist."""
    missing = []
    for f in files:
        if not (project_path / f).exists():
            missing.append(f)
    if missing:
        return False, f"Missing files: {missing}"
    return True, f"All {len(files)} files exist"


def validate_code_imports_module(project_path: Path, filename: str, module: str) -> tuple[bool, str]:
    """Check if code imports a specific module."""
    import re
    filepath = project_path / filename
    if not filepath.exists():
        return False, f"File {filename} not found"

    content = filepath.read_text()
    patterns = [
        rf"import\s+{module}",
        rf"from\s+{module}\s+import",
    ]
    for pattern in patterns:
        if re.search(pattern, content):
            return True, f"{filename} imports {module}"
    return False, f"{filename} does not import {module}"


def validate_error_handling(project_path: Path, filename: str) -> tuple[bool, str]:
    """Check if code has proper error handling."""
    import re
    filepath = project_path / filename
    if not filepath.exists():
        return False, f"File {filename} not found"

    content = filepath.read_text()
    has_try = bool(re.search(r"try:", content))
    has_except = bool(re.search(r"except\s+\w+", content))

    if has_try and has_except:
        return True, f"{filename} has error handling"
    return False, f"{filename} lacks proper error handling"


def validate_async_code(project_path: Path, filename: str) -> tuple[bool, str]:
    """Check if code uses async/await properly."""
    import re
    filepath = project_path / filename
    if not filepath.exists():
        return False, f"File {filename} not found"

    content = filepath.read_text()
    has_async = bool(re.search(r"async\s+def", content))
    has_await = bool(re.search(r"await\s+", content))

    if has_async and has_await:
        return True, f"{filename} uses async/await"
    return False, f"{filename} missing async/await patterns"


def validate_type_hints(project_path: Path, filename: str) -> tuple[bool, str]:
    """Check if functions have type hints."""
    import re
    filepath = project_path / filename
    if not filepath.exists():
        return False, f"File {filename} not found"

    content = filepath.read_text()
    # Find function definitions
    func_pattern = r"def\s+\w+\([^)]*\)"
    functions = re.findall(func_pattern, content)

    # Check for type hints (-> or : type in parameters)
    typed_pattern = r"def\s+\w+\([^)]*:\s*\w+[^)]*\)|def\s+\w+\([^)]*\)\s*->"
    typed_functions = re.findall(typed_pattern, content)

    if len(functions) == 0:
        return False, f"No functions found in {filename}"

    ratio = len(typed_functions) / len(functions)
    if ratio >= 0.5:  # At least 50% of functions should have type hints
        return True, f"{filename} has type hints ({len(typed_functions)}/{len(functions)} functions)"
    return False, f"{filename} lacks type hints ({len(typed_functions)}/{len(functions)} functions)"


def validate_docstrings(project_path: Path, filename: str) -> tuple[bool, str]:
    """Check if classes/functions have docstrings."""
    import ast
    filepath = project_path / filename
    if not filepath.exists():
        return False, f"File {filename} not found"

    try:
        content = filepath.read_text()
        tree = ast.parse(content)

        total = 0
        with_docstring = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                total += 1
                if ast.get_docstring(node):
                    with_docstring += 1

        if total == 0:
            return False, f"No functions/classes in {filename}"

        ratio = with_docstring / total
        if ratio >= 0.5:
            return True, f"{filename} has docstrings ({with_docstring}/{total})"
        return False, f"{filename} lacks docstrings ({with_docstring}/{total})"
    except SyntaxError:
        return False, f"Syntax error in {filename}"


# Register new validators
VALIDATORS.update({
    "multiple_files_exist": validate_multiple_files_exist,
    "code_imports_module": validate_code_imports_module,
    "error_handling": validate_error_handling,
    "async_code": validate_async_code,
    "type_hints": validate_type_hints,
    "docstrings": validate_docstrings,
})


# ===========================================
# Agent Chain Test Cases
# ===========================================

AGENT_CHAIN_TESTS: list[TestCase] = [
    # ========== COLLABORATION TESTS ==========
    TestCase(
        id="collab-001",
        name="Multi-file Refactoring",
        category=CATEGORY_COLLABORATION,
        prompt="""Refaktorera denna kodbas som har tre sammanlänkade filer:

1. models.py - Datamodeller
2. services.py - Business logic som använder models
3. api.py - API endpoints som använder services

Kravet är att:
- Lägg till Pydantic BaseModel för alla modeller
- Lägg till felhantering i services
- Lägg till validering i API endpoints

Alla filer måste synka korrekt med varandra.""",
        validators=[
            {"type": "file_exists", "filename": "models.py"},
            {"type": "file_exists", "filename": "services.py"},
            {"type": "file_exists", "filename": "api.py"},
            {"type": "python_syntax", "filename": "models.py"},
            {"type": "python_syntax", "filename": "services.py"},
            {"type": "python_syntax", "filename": "api.py"},
            {"type": "file_contains", "filename": "models.py", "pattern": r"BaseModel|dataclass"},
            {"type": "error_handling", "filename": "services.py"},
        ],
        difficulty="hard",
        points=30,
    ),
    TestCase(
        id="collab-002",
        name="Executor Asks Reviewer",
        category=CATEGORY_COLLABORATION,
        prompt="""Skapa en komplex klass som kräver noggrant code review:

Implementera en `CacheManager` klass med:
- LRU cache implementation
- Thread-safe operationer
- TTL (time-to-live) för cache entries
- Metrics för cache hits/misses

Koden måste vara så välskriven att den skulle klara en rigorös code review.""",
        validators=[
            {"type": "file_exists", "filename": "cache_manager.py"},
            {"type": "python_syntax", "filename": "cache_manager.py"},
            {"type": "class_exists", "filename": "cache_manager.py", "class_name": "CacheManager"},
            {"type": "file_contains", "filename": "cache_manager.py", "pattern": r"Lock|RLock|threading"},
            {"type": "file_contains", "filename": "cache_manager.py", "pattern": r"ttl|TTL|expire"},
            {"type": "docstrings", "filename": "cache_manager.py"},
            {"type": "type_hints", "filename": "cache_manager.py"},
        ],
        difficulty="hard",
        points=35,
    ),
    TestCase(
        id="collab-003",
        name="Design Discussion",
        category=CATEGORY_COLLABORATION,
        prompt="""Designa och implementera ett plugin-system för en applikation.

Systemet ska ha:
1. base.py - Abstract base class för plugins
2. loader.py - Plugin discovery och loading
3. registry.py - Plugin registration och lifecycle
4. examples/hello_plugin.py - Exempelplugin

Plugins ska kunna:
- Registrera sig automatiskt
- Ha hooks för startup/shutdown
- Deklarera dependencies på andra plugins""",
        validators=[
            {"type": "file_exists", "filename": "base.py"},
            {"type": "file_exists", "filename": "loader.py"},
            {"type": "file_exists", "filename": "registry.py"},
            {"type": "python_syntax", "filename": "base.py"},
            {"type": "python_syntax", "filename": "loader.py"},
            {"type": "python_syntax", "filename": "registry.py"},
            {"type": "file_contains", "filename": "base.py", "pattern": r"ABC|abstractmethod"},
            {"type": "file_contains", "filename": "loader.py", "pattern": r"import|load|discover"},
            {"type": "file_contains", "filename": "registry.py", "pattern": r"register|Registry"},
        ],
        difficulty="hard",
        points=40,
    ),

    # ========== RECOVERY TESTS ==========
    TestCase(
        id="recovery-001",
        name="Handle Invalid Input Gracefully",
        category=CATEGORY_RECOVERY,
        prompt="""Skapa en robust input parser som hanterar alla typer av felaktig input:

parser.py ska kunna:
- Parsa JSON, YAML, och TOML
- Ge tydliga felmeddelanden vid parse-fel
- Ha fallback-värden för saknade fält
- Logga alla parsing-försök

Inkludera tests för edge cases.""",
        validators=[
            {"type": "file_exists", "filename": "parser.py"},
            {"type": "python_syntax", "filename": "parser.py"},
            {"type": "error_handling", "filename": "parser.py"},
            {"type": "file_contains", "filename": "parser.py", "pattern": r"json|JSON"},
            {"type": "file_contains", "filename": "parser.py", "pattern": r"except|Error|Exception"},
            {"type": "file_contains", "filename": "parser.py", "pattern": r"logging|logger|log"},
        ],
        difficulty="medium",
        points=25,
    ),
    TestCase(
        id="recovery-002",
        name="Retry Logic Implementation",
        category=CATEGORY_RECOVERY,
        prompt="""Implementera ett retry-system för externa API-anrop:

retry.py ska ha:
- Configurable retry count och delay
- Exponential backoff
- Circuit breaker pattern
- Olika strategier för olika feltyper

client.py ska använda retry.py för HTTP requests.""",
        validators=[
            {"type": "file_exists", "filename": "retry.py"},
            {"type": "file_exists", "filename": "client.py"},
            {"type": "python_syntax", "filename": "retry.py"},
            {"type": "python_syntax", "filename": "client.py"},
            {"type": "file_contains", "filename": "retry.py", "pattern": r"retry|Retry"},
            {"type": "file_contains", "filename": "retry.py", "pattern": r"backoff|delay|sleep"},
            {"type": "file_contains", "filename": "retry.py", "pattern": r"max_retries|max_attempts|count"},
        ],
        difficulty="medium",
        points=25,
    ),
    TestCase(
        id="recovery-003",
        name="Graceful Degradation",
        category=CATEGORY_RECOVERY,
        prompt="""Skapa ett system som degraderar gracefully när dependencies inte är tillgängliga:

service.py ska:
- Ha primary och fallback data sources
- Automatiskt switcha till fallback vid fel
- Cacha resultat för offline-läge
- Logga alla state changes

Inkludera health check functionality.""",
        validators=[
            {"type": "file_exists", "filename": "service.py"},
            {"type": "python_syntax", "filename": "service.py"},
            {"type": "error_handling", "filename": "service.py"},
            {"type": "file_contains", "filename": "service.py", "pattern": r"fallback|backup|alternative"},
            {"type": "file_contains", "filename": "service.py", "pattern": r"cache|Cache"},
            {"type": "file_contains", "filename": "service.py", "pattern": r"health|status|check"},
        ],
        difficulty="hard",
        points=30,
    ),

    # ========== PARALLEL EXECUTION TESTS ==========
    TestCase(
        id="parallel-001",
        name="Concurrent File Processing",
        category=CATEGORY_PARALLEL,
        prompt="""Skapa ett system för concurrent fil-processering:

processor.py ska:
- Processa flera filer parallellt
- Ha configurable worker count
- Visa progress för varje fil
- Aggregera resultat från alla workers

Använd asyncio eller concurrent.futures.""",
        validators=[
            {"type": "file_exists", "filename": "processor.py"},
            {"type": "python_syntax", "filename": "processor.py"},
            {"type": "file_contains", "filename": "processor.py", "pattern": r"asyncio|concurrent|ThreadPool|ProcessPool"},
            {"type": "file_contains", "filename": "processor.py", "pattern": r"gather|map|submit|as_completed"},
            {"type": "file_contains", "filename": "processor.py", "pattern": r"worker|Worker|workers"},
        ],
        difficulty="medium",
        points=25,
    ),
    TestCase(
        id="parallel-002",
        name="Async Web Scraper",
        category=CATEGORY_PARALLEL,
        prompt="""Implementera en asynkron web scraper:

async_scraper.py ska:
- Scrapa flera URLs parallellt med aiohttp/httpx
- Ha rate limiting per domain
- Respektera robots.txt
- Hantera timeouts gracefully
- Spara resultat progressivt

Målet är att scrapa 10+ URLs effektivt.""",
        validators=[
            {"type": "file_exists", "filename": "async_scraper.py"},
            {"type": "python_syntax", "filename": "async_scraper.py"},
            {"type": "async_code", "filename": "async_scraper.py"},
            {"type": "file_contains", "filename": "async_scraper.py", "pattern": r"aiohttp|httpx"},
            {"type": "file_contains", "filename": "async_scraper.py", "pattern": r"gather|create_task|semaphore|Semaphore"},
            {"type": "error_handling", "filename": "async_scraper.py"},
        ],
        difficulty="hard",
        points=35,
    ),
    TestCase(
        id="parallel-003",
        name="Producer-Consumer Pipeline",
        category=CATEGORY_PARALLEL,
        prompt="""Skapa en producer-consumer pipeline med asyncio:

pipeline.py ska ha:
- Producer som genererar data
- Multiple consumers som processar data
- Async queue för kommunikation
- Graceful shutdown
- Backpressure handling

Inkludera metrics för throughput.""",
        validators=[
            {"type": "file_exists", "filename": "pipeline.py"},
            {"type": "python_syntax", "filename": "pipeline.py"},
            {"type": "async_code", "filename": "pipeline.py"},
            {"type": "file_contains", "filename": "pipeline.py", "pattern": r"Queue|queue"},
            {"type": "file_contains", "filename": "pipeline.py", "pattern": r"producer|Producer"},
            {"type": "file_contains", "filename": "pipeline.py", "pattern": r"consumer|Consumer"},
        ],
        difficulty="hard",
        points=35,
    ),

    # ========== FULL CHAIN TESTS ==========
    TestCase(
        id="chain-001",
        name="Complete CRUD Application",
        category=CATEGORY_CHAIN,
        prompt="""Skapa en komplett CRUD-applikation med följande arkitektur:

1. models/user.py - User model med Pydantic
2. repositories/user_repo.py - Data access layer
3. services/user_service.py - Business logic
4. api/routes.py - FastAPI routes
5. tests/test_user.py - Unit tests

Hela kedjan ska fungera tillsammans med:
- Proper error handling på varje nivå
- Type hints överallt
- Docstrings för public methods""",
        validators=[
            {"type": "file_exists", "filename": "models/user.py"},
            {"type": "file_exists", "filename": "repositories/user_repo.py"},
            {"type": "file_exists", "filename": "services/user_service.py"},
            {"type": "file_exists", "filename": "api/routes.py"},
            {"type": "python_syntax", "filename": "models/user.py"},
            {"type": "python_syntax", "filename": "repositories/user_repo.py"},
            {"type": "python_syntax", "filename": "services/user_service.py"},
            {"type": "python_syntax", "filename": "api/routes.py"},
            {"type": "file_contains", "filename": "models/user.py", "pattern": r"BaseModel|pydantic"},
            {"type": "error_handling", "filename": "services/user_service.py"},
            {"type": "file_contains", "filename": "api/routes.py", "pattern": r"FastAPI|APIRouter"},
        ],
        difficulty="hard",
        points=50,
    ),
    TestCase(
        id="chain-002",
        name="Event-Driven Microservice",
        category=CATEGORY_CHAIN,
        prompt="""Bygg en event-driven microservice:

1. events/base.py - Event base class och types
2. events/bus.py - Event bus implementation
3. handlers/order_handler.py - Order event handlers
4. services/order_service.py - Order business logic
5. main.py - Application entry point

Features:
- Async event processing
- Event replay capability
- Dead letter queue för failed events
- Structured logging""",
        validators=[
            {"type": "file_exists", "filename": "events/base.py"},
            {"type": "file_exists", "filename": "events/bus.py"},
            {"type": "file_exists", "filename": "handlers/order_handler.py"},
            {"type": "file_exists", "filename": "services/order_service.py"},
            {"type": "file_exists", "filename": "main.py"},
            {"type": "python_syntax", "filename": "events/base.py"},
            {"type": "python_syntax", "filename": "events/bus.py"},
            {"type": "async_code", "filename": "events/bus.py"},
            {"type": "file_contains", "filename": "events/base.py", "pattern": r"Event|EventType"},
            {"type": "file_contains", "filename": "events/bus.py", "pattern": r"subscribe|publish|emit"},
        ],
        difficulty="hard",
        points=50,
    ),
    TestCase(
        id="chain-003",
        name="CLI with Multiple Commands",
        category=CATEGORY_CHAIN,
        prompt="""Skapa ett CLI-verktyg med flera subcommands:

1. cli/main.py - Main entry point med typer/click
2. cli/commands/init.py - Initialize project
3. cli/commands/build.py - Build command
4. cli/commands/deploy.py - Deploy command
5. cli/utils/config.py - Configuration handling
6. cli/utils/logging.py - Logging setup

Features:
- Global options (--verbose, --config)
- Command-specific options
- Config file support (YAML)
- Colored output""",
        validators=[
            {"type": "file_exists", "filename": "cli/main.py"},
            {"type": "file_exists", "filename": "cli/commands/init.py"},
            {"type": "file_exists", "filename": "cli/commands/build.py"},
            {"type": "file_exists", "filename": "cli/utils/config.py"},
            {"type": "python_syntax", "filename": "cli/main.py"},
            {"type": "python_syntax", "filename": "cli/commands/init.py"},
            {"type": "python_syntax", "filename": "cli/utils/config.py"},
            {"type": "file_contains", "filename": "cli/main.py", "pattern": r"typer|click|argparse"},
            {"type": "file_contains", "filename": "cli/utils/config.py", "pattern": r"yaml|YAML|toml|json"},
        ],
        difficulty="hard",
        points=45,
    ),
]


# ===========================================
# Agent Chain Eval Runner
# ===========================================

class AgentChainEvalRunner:
    """Runs agent chain evaluation tests."""

    def __init__(self, agentfarm_path: str = None):
        self.agentfarm_path = Path(agentfarm_path or Path(__file__).parent.parent)
        self.results_dir = self.agentfarm_path / "evals" / "results"
        self.results_dir.mkdir(exist_ok=True)

    async def run_test(self, test: TestCase, verbose: bool = False) -> TestResult:
        """Run a single test case."""
        start_time = time.time()
        errors = []
        validator_results = []

        with tempfile.TemporaryDirectory(prefix=f"eval_{test.id}_") as tmpdir:
            project_path = Path(tmpdir)

            try:
                # Run AgentFarm workflow
                await self._run_workflow(test.prompt, project_path, verbose)

                # Run validators
                for validator in test.validators:
                    v_type = validator["type"]
                    v_func = VALIDATORS.get(v_type)

                    if not v_func:
                        errors.append(f"Unknown validator: {v_type}")
                        validator_results.append(False)
                        continue

                    v_args = {k: v for k, v in validator.items() if k != "type"}

                    try:
                        passed, message = v_func(project_path, **v_args)
                        validator_results.append(passed)
                        if not passed:
                            errors.append(message)
                        elif verbose:
                            print(f"       + {message}")
                    except Exception as e:
                        validator_results.append(False)
                        errors.append(f"Validator error: {e}")

            except asyncio.TimeoutError:
                errors.append(f"Test timed out after {test.timeout}s")
                validator_results = [False] * len(test.validators)
            except Exception as e:
                errors.append(f"Workflow error: {e}")
                validator_results = [False] * len(test.validators)

        duration = time.time() - start_time

        if validator_results:
            score = sum(validator_results) / len(validator_results)
        else:
            score = 0.0

        passed = score >= 0.7  # 70% threshold for chain tests (harder)

        return TestResult(
            test_id=test.id,
            passed=passed,
            score=score,
            duration=duration,
            errors=errors,
            details={
                "validators_passed": sum(validator_results),
                "validators_total": len(validator_results),
                "category": test.category,
            }
        )

    async def _run_workflow(self, prompt: str, project_path: Path, verbose: bool = False):
        """Run AgentFarm workflow."""
        from agentfarm.orchestrator import Orchestrator
        from agentfarm.tools.file_tools import FileTools

        orchestrator = Orchestrator(
            provider=None,
            working_dir=str(project_path),
            use_multi_provider=True,
        )

        file_tools = FileTools(str(project_path))
        orchestrator.inject_tools(file_tools=file_tools)

        if verbose:
            print("       Running workflow...")

        await asyncio.wait_for(
            orchestrator.run_workflow(prompt),
            timeout=600  # 10 minute timeout for complex tasks
        )

    async def run_all(self, category: str = None, quick: bool = False) -> EvalReport:
        """Run all agent chain tests."""
        tests = AGENT_CHAIN_TESTS
        if category:
            tests = [t for t in tests if t.category == category]

        if quick:
            # Run only one test per category for quick validation
            seen_categories = set()
            filtered_tests = []
            for t in tests:
                if t.category not in seen_categories:
                    filtered_tests.append(t)
                    seen_categories.add(t.category)
            tests = filtered_tests

        print(f"\n{'='*60}")
        print(f"  AGENT CHAIN EVALUATION SUITE")
        print(f"{'='*60}")
        print(f"  Tests: {len(tests)}")
        print(f"  Category: {category or 'ALL'}")
        print(f"  Mode: {'QUICK' if quick else 'FULL'}")
        print(f"{'='*60}\n")

        results = []
        start_time = time.time()

        for i, test in enumerate(tests, 1):
            print(f"[{i}/{len(tests)}] {test.name} ({test.category})...", end=" ", flush=True)

            result = await self.run_test(test)
            results.append(result)

            status = "PASS" if result.passed else "FAIL"
            print(f"{status} ({result.score:.0%}, {result.duration:.1f}s)")

            if result.errors:
                for error in result.errors[:3]:
                    print(f"       - {error[:80]}")

        total_duration = time.time() - start_time

        passed = sum(1 for r in results if r.passed)

        test_map = {t.id: t for t in tests}
        total_score = sum(r.score * test_map[r.test_id].points for r in results if r.test_id in test_map)
        max_score = sum(t.points for t in tests)

        # By category
        by_category = {}
        for cat in [CATEGORY_COLLABORATION, CATEGORY_RECOVERY, CATEGORY_PARALLEL, CATEGORY_CHAIN]:
            cat_results = [r for r in results if r.details.get("category") == cat]
            if cat_results:
                by_category[cat] = {
                    "total": len(cat_results),
                    "passed": sum(1 for r in cat_results if r.passed),
                    "avg_score": sum(r.score for r in cat_results) / len(cat_results),
                }

        report = EvalReport(
            timestamp=datetime.now().isoformat(),
            total_tests=len(tests),
            passed=passed,
            failed=len(tests) - passed,
            total_score=total_score,
            max_score=max_score,
            percentage=total_score / max_score * 100 if max_score > 0 else 0,
            duration=total_duration,
            results=results,
            by_category=by_category,
        )

        print(f"\n{'='*60}")
        print(f"  AGENT CHAIN RESULTS")
        print(f"{'='*60}")
        print(f"  Passed: {passed}/{len(tests)}")
        print(f"  Score:  {total_score:.1f}/{max_score} ({report.percentage:.1f}%)")
        print(f"  Time:   {total_duration:.1f}s ({total_duration/60:.1f} min)")
        print()
        print("  By Category:")
        for cat, stats in by_category.items():
            print(f"    {cat}: {stats['passed']}/{stats['total']} ({stats['avg_score']:.0%})")
        print(f"{'='*60}\n")

        # Save report
        report_path = self.results_dir / f"agent_chain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w") as f:
            json.dump({
                "timestamp": report.timestamp,
                "type": "agent_chain",
                "total_tests": report.total_tests,
                "passed": report.passed,
                "failed": report.failed,
                "total_score": report.total_score,
                "max_score": report.max_score,
                "percentage": report.percentage,
                "duration": report.duration,
                "by_category": report.by_category,
                "results": [
                    {
                        "test_id": r.test_id,
                        "passed": r.passed,
                        "score": r.score,
                        "duration": r.duration,
                        "errors": r.errors,
                        "details": r.details,
                    }
                    for r in results
                ],
            }, f, indent=2)

        print(f"  Report saved: {report_path}")

        return report

    def list_tests(self):
        """List all available agent chain tests."""
        print(f"\n{'='*60}")
        print(f"  AGENT CHAIN TESTS")
        print(f"{'='*60}\n")

        categories = [CATEGORY_COLLABORATION, CATEGORY_RECOVERY, CATEGORY_PARALLEL, CATEGORY_CHAIN]
        for cat in categories:
            tests = [t for t in AGENT_CHAIN_TESTS if t.category == cat]
            if tests:
                print(f"  {cat.upper()}:")
                for t in tests:
                    print(f"    [{t.id}] {t.name} ({t.difficulty}, {t.points}pts)")
                print()

        total_points = sum(t.points for t in AGENT_CHAIN_TESTS)
        print(f"  Total: {len(AGENT_CHAIN_TESTS)} tests, {total_points} points\n")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="AgentFarm Agent Chain Evaluation")
    parser.add_argument("--category", "-c",
                        choices=["collaboration", "recovery", "parallel", "chain"],
                        help="Run only tests in this category")
    parser.add_argument("--list", "-l", action="store_true", help="List all tests")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick mode (one test per category)")
    parser.add_argument("--test", "-t", help="Run a specific test by ID")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    runner = AgentChainEvalRunner()

    if args.list:
        runner.list_tests()
        return

    if args.test:
        test = next((t for t in AGENT_CHAIN_TESTS if t.id == args.test), None)
        if not test:
            print(f"Test not found: {args.test}")
            return
        result = asyncio.run(runner.run_test(test, verbose=args.verbose))
        print(f"\nResult: {'PASS' if result.passed else 'FAIL'} ({result.score:.0%})")
        if result.errors:
            print("Errors:")
            for e in result.errors:
                print(f"  - {e}")
    else:
        asyncio.run(runner.run_all(category=args.category, quick=args.quick))


if __name__ == "__main__":
    main()
