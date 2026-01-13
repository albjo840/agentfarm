"""
AgentFarm Evaluation Suite

Tests agent capabilities across multiple dimensions:
- Code generation
- Bug fixing
- Refactoring
- Multi-step tasks

Usage:
    python -m evals.suite                    # Run all tests
    python -m evals.suite --category codegen # Run specific category
    python -m evals.suite --list             # List all tests
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# Eval categories
CATEGORY_CODEGEN = "codegen"
CATEGORY_BUGFIX = "bugfix"
CATEGORY_REFACTOR = "refactor"
CATEGORY_MULTISTEP = "multistep"


@dataclass
class TestCase:
    """A single evaluation test case."""
    id: str
    name: str
    category: str
    prompt: str
    validators: list[dict[str, Any]]
    expected_files: list[str] = field(default_factory=list)
    timeout: int = 300  # 5 minutes default
    difficulty: str = "medium"  # easy, medium, hard
    points: int = 10


@dataclass
class TestResult:
    """Result of running a test case."""
    test_id: str
    passed: bool
    score: float  # 0.0 to 1.0
    duration: float
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalReport:
    """Full evaluation report."""
    timestamp: str
    total_tests: int
    passed: int
    failed: int
    total_score: float
    max_score: float
    percentage: float
    duration: float
    results: list[TestResult] = field(default_factory=list)
    by_category: dict[str, dict] = field(default_factory=dict)


# ===========================================
# Validators
# ===========================================

def validate_file_exists(project_path: Path, filename: str) -> tuple[bool, str]:
    """Check if a file exists in the project."""
    filepath = project_path / filename
    if filepath.exists():
        return True, f"File {filename} exists"
    return False, f"File {filename} not found"


def validate_file_contains(project_path: Path, filename: str, pattern: str) -> tuple[bool, str]:
    """Check if a file contains a regex pattern."""
    filepath = project_path / filename
    if not filepath.exists():
        return False, f"File {filename} not found"

    content = filepath.read_text()
    if re.search(pattern, content):
        return True, f"Pattern '{pattern}' found in {filename}"
    return False, f"Pattern '{pattern}' not found in {filename}"


def validate_python_syntax(project_path: Path, filename: str) -> tuple[bool, str]:
    """Check if Python file has valid syntax."""
    filepath = project_path / filename
    if not filepath.exists():
        return False, f"File {filename} not found"

    try:
        result = subprocess.run(
            ["python", "-m", "py_compile", str(filepath)],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return True, f"{filename} has valid Python syntax"
        return False, f"Syntax error: {result.stderr}"
    except Exception as e:
        return False, f"Error checking syntax: {e}"


def validate_tests_pass(project_path: Path, test_file: str = None) -> tuple[bool, str]:
    """Run pytest and check if tests pass."""
    try:
        cmd = ["python", "-m", "pytest", "-v"]
        if test_file:
            cmd.append(str(project_path / test_file))
        else:
            cmd.append(str(project_path))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_path
        )

        if result.returncode == 0:
            return True, "All tests passed"
        return False, f"Tests failed: {result.stdout[-500:]}"
    except subprocess.TimeoutExpired:
        return False, "Tests timed out"
    except Exception as e:
        return False, f"Error running tests: {e}"


def validate_function_exists(project_path: Path, filename: str, function_name: str) -> tuple[bool, str]:
    """Check if a function exists in a Python file."""
    filepath = project_path / filename
    if not filepath.exists():
        return False, f"File {filename} not found"

    content = filepath.read_text()
    pattern = rf"def\s+{function_name}\s*\("
    if re.search(pattern, content):
        return True, f"Function {function_name} found in {filename}"
    return False, f"Function {function_name} not found in {filename}"


def validate_class_exists(project_path: Path, filename: str, class_name: str) -> tuple[bool, str]:
    """Check if a class exists in a Python file."""
    filepath = project_path / filename
    if not filepath.exists():
        return False, f"File {filename} not found"

    content = filepath.read_text()
    pattern = rf"class\s+{class_name}\s*[:\(]"
    if re.search(pattern, content):
        return True, f"Class {class_name} found in {filename}"
    return False, f"Class {class_name} not found in {filename}"


def validate_no_errors_in_output(project_path: Path, command: list[str]) -> tuple[bool, str]:
    """Run a command and check for no errors."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_path
        )
        if result.returncode == 0:
            return True, "Command ran without errors"
        return False, f"Command failed: {result.stderr[:500]}"
    except Exception as e:
        return False, f"Error: {e}"


VALIDATORS = {
    "file_exists": validate_file_exists,
    "file_contains": validate_file_contains,
    "python_syntax": validate_python_syntax,
    "tests_pass": validate_tests_pass,
    "function_exists": validate_function_exists,
    "class_exists": validate_class_exists,
    "no_errors": validate_no_errors_in_output,
}


# ===========================================
# Test Cases
# ===========================================

TEST_CASES: list[TestCase] = [
    # ========== CODE GENERATION ==========
    TestCase(
        id="codegen-001",
        name="Simple Function",
        category=CATEGORY_CODEGEN,
        prompt="Skapa en Python-fil med en funktion 'is_prime(n)' som returnerar True om n är ett primtal, annars False. Inkludera docstring och typehints.",
        validators=[
            {"type": "file_exists", "filename": "prime.py"},
            {"type": "python_syntax", "filename": "prime.py"},
            {"type": "function_exists", "filename": "prime.py", "function_name": "is_prime"},
            {"type": "file_contains", "filename": "prime.py", "pattern": r"def is_prime\(n:\s*int\)"},
            {"type": "file_contains", "filename": "prime.py", "pattern": r'""".*"""'},
        ],
        difficulty="easy",
        points=10,
    ),
    TestCase(
        id="codegen-002",
        name="Calculator Class",
        category=CATEGORY_CODEGEN,
        prompt="Skapa en Calculator-klass i Python med metoderna add, subtract, multiply och divide. Divide ska hantera division med noll. Inkludera enhetstester.",
        validators=[
            {"type": "file_exists", "filename": "calculator.py"},
            {"type": "python_syntax", "filename": "calculator.py"},
            {"type": "class_exists", "filename": "calculator.py", "class_name": "Calculator"},
            {"type": "function_exists", "filename": "calculator.py", "function_name": "add"},
            {"type": "function_exists", "filename": "calculator.py", "function_name": "divide"},
            {"type": "file_contains", "filename": "calculator.py", "pattern": r"ZeroDivisionError|zero|0"},
        ],
        difficulty="easy",
        points=15,
    ),
    TestCase(
        id="codegen-003",
        name="REST API Endpoint",
        category=CATEGORY_CODEGEN,
        prompt="Skapa ett enkelt Flask REST API med endpoints: GET /items (lista), POST /items (skapa), GET /items/<id> (hämta en). Använd en in-memory lista som databas.",
        validators=[
            {"type": "file_exists", "filename": "app.py"},
            {"type": "python_syntax", "filename": "app.py"},
            {"type": "file_contains", "filename": "app.py", "pattern": r"from flask import"},
            {"type": "file_contains", "filename": "app.py", "pattern": r"@app\.route.*items"},
            {"type": "file_contains", "filename": "app.py", "pattern": r"methods=\[.*GET"},
            {"type": "file_contains", "filename": "app.py", "pattern": r"methods=\[.*POST"},
        ],
        difficulty="medium",
        points=20,
    ),
    TestCase(
        id="codegen-004",
        name="Data Processing Pipeline",
        category=CATEGORY_CODEGEN,
        prompt="Skapa en databehandlingspipeline som: 1) Läser CSV-data, 2) Filtrerar rader baserat på villkor, 3) Transformerar data, 4) Sparar till ny CSV. Använd pandas.",
        validators=[
            {"type": "file_exists", "filename": "pipeline.py"},
            {"type": "python_syntax", "filename": "pipeline.py"},
            {"type": "file_contains", "filename": "pipeline.py", "pattern": r"import pandas|from pandas"},
            {"type": "file_contains", "filename": "pipeline.py", "pattern": r"read_csv"},
            {"type": "file_contains", "filename": "pipeline.py", "pattern": r"to_csv"},
        ],
        difficulty="medium",
        points=20,
    ),

    # ========== BUG FIXING ==========
    TestCase(
        id="bugfix-001",
        name="Fix Off-by-One Error",
        category=CATEGORY_BUGFIX,
        prompt="""Fixa buggen i denna kod. Filen heter buggy.py:

```python
def get_last_n_items(items, n):
    '''Returns the last n items from a list'''
    return items[-n:-1]  # BUG: Returns wrong items

# Test: get_last_n_items([1,2,3,4,5], 2) should return [4, 5]
```

Skapa filen med den fixade koden.""",
        validators=[
            {"type": "file_exists", "filename": "buggy.py"},
            {"type": "python_syntax", "filename": "buggy.py"},
            {"type": "file_contains", "filename": "buggy.py", "pattern": r"items\[-n:\]|items\[len\(items\)-n:\]"},
        ],
        difficulty="easy",
        points=10,
    ),
    TestCase(
        id="bugfix-002",
        name="Fix Race Condition",
        category=CATEGORY_BUGFIX,
        prompt="""Fixa race condition i denna kod. Filen heter counter.py:

```python
import threading

counter = 0

def increment():
    global counter
    for _ in range(100000):
        counter += 1  # BUG: Not thread-safe

threads = [threading.Thread(target=increment) for _ in range(4)]
```

Lägg till korrekt locking för thread-safety.""",
        validators=[
            {"type": "file_exists", "filename": "counter.py"},
            {"type": "python_syntax", "filename": "counter.py"},
            {"type": "file_contains", "filename": "counter.py", "pattern": r"Lock|RLock|lock\.acquire|with.*lock"},
        ],
        difficulty="medium",
        points=15,
    ),
    TestCase(
        id="bugfix-003",
        name="Fix SQL Injection",
        category=CATEGORY_BUGFIX,
        prompt="""Fixa SQL injection-sårbarheten i denna kod. Filen heter db.py:

```python
import sqlite3

def get_user(username):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # BUG: SQL Injection vulnerability!
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
    return cursor.fetchone()
```

Använd parameteriserade queries.""",
        validators=[
            {"type": "file_exists", "filename": "db.py"},
            {"type": "python_syntax", "filename": "db.py"},
            {"type": "file_contains", "filename": "db.py", "pattern": r"execute\([^,]+,\s*[\(\[]"},
            {"type": "file_contains", "filename": "db.py", "pattern": r"\?|%s|:\w+"},
        ],
        difficulty="medium",
        points=15,
    ),

    # ========== REFACTORING ==========
    TestCase(
        id="refactor-001",
        name="Extract Method",
        category=CATEGORY_REFACTOR,
        prompt="""Refaktorera denna kod genom att extrahera metoder. Filen heter messy.py:

```python
def process_order(order):
    # Calculate total
    total = 0
    for item in order['items']:
        total += item['price'] * item['quantity']

    # Apply discount
    if order.get('discount_code') == 'SAVE10':
        total = total * 0.9
    elif order.get('discount_code') == 'SAVE20':
        total = total * 0.8

    # Calculate tax
    tax = total * 0.25
    total_with_tax = total + tax

    # Format receipt
    receipt = f"Order #{order['id']}\\n"
    for item in order['items']:
        receipt += f"  {item['name']}: {item['price']} x {item['quantity']}\\n"
    receipt += f"Total: {total_with_tax}"

    return receipt
```

Extrahera till separata funktioner: calculate_subtotal, apply_discount, calculate_tax, format_receipt.""",
        validators=[
            {"type": "file_exists", "filename": "messy.py"},
            {"type": "python_syntax", "filename": "messy.py"},
            {"type": "function_exists", "filename": "messy.py", "function_name": "calculate_subtotal"},
            {"type": "function_exists", "filename": "messy.py", "function_name": "apply_discount"},
            {"type": "function_exists", "filename": "messy.py", "function_name": "calculate_tax"},
            {"type": "function_exists", "filename": "messy.py", "function_name": "format_receipt"},
        ],
        difficulty="medium",
        points=20,
    ),
    TestCase(
        id="refactor-002",
        name="Replace Conditionals with Polymorphism",
        category=CATEGORY_REFACTOR,
        prompt="""Refaktorera denna kod att använda polymorfism istället för if-satser. Filen heter shapes.py:

```python
def calculate_area(shape):
    if shape['type'] == 'circle':
        return 3.14159 * shape['radius'] ** 2
    elif shape['type'] == 'rectangle':
        return shape['width'] * shape['height']
    elif shape['type'] == 'triangle':
        return 0.5 * shape['base'] * shape['height']
    else:
        raise ValueError(f"Unknown shape: {shape['type']}")
```

Skapa en Shape-basklass med Circle, Rectangle och Triangle som subklasser.""",
        validators=[
            {"type": "file_exists", "filename": "shapes.py"},
            {"type": "python_syntax", "filename": "shapes.py"},
            {"type": "class_exists", "filename": "shapes.py", "class_name": "Shape"},
            {"type": "class_exists", "filename": "shapes.py", "class_name": "Circle"},
            {"type": "class_exists", "filename": "shapes.py", "class_name": "Rectangle"},
            {"type": "class_exists", "filename": "shapes.py", "class_name": "Triangle"},
            {"type": "file_contains", "filename": "shapes.py", "pattern": r"def area\(self\)"},
        ],
        difficulty="medium",
        points=20,
    ),

    # ========== MULTI-STEP ==========
    TestCase(
        id="multistep-001",
        name="CLI Todo App",
        category=CATEGORY_MULTISTEP,
        prompt="""Skapa en komplett CLI todo-applikation med följande:

1. todo.py - Huvudfil med CLI (argparse)
2. storage.py - JSON-baserad lagring
3. models.py - Pydantic-modeller för Todo-items

Features:
- todo add "task description"
- todo list
- todo complete <id>
- todo delete <id>

Inkludera README.md med användningsinstruktioner.""",
        validators=[
            {"type": "file_exists", "filename": "todo.py"},
            {"type": "file_exists", "filename": "storage.py"},
            {"type": "file_exists", "filename": "models.py"},
            {"type": "file_exists", "filename": "README.md"},
            {"type": "python_syntax", "filename": "todo.py"},
            {"type": "python_syntax", "filename": "storage.py"},
            {"type": "python_syntax", "filename": "models.py"},
            {"type": "file_contains", "filename": "todo.py", "pattern": r"argparse|click|typer"},
            {"type": "file_contains", "filename": "storage.py", "pattern": r"json"},
            {"type": "file_contains", "filename": "models.py", "pattern": r"pydantic|dataclass"},
        ],
        difficulty="hard",
        points=30,
    ),
    TestCase(
        id="multistep-002",
        name="Web Scraper with Tests",
        category=CATEGORY_MULTISTEP,
        prompt="""Skapa en web scraper med:

1. scraper.py - Huvudklass WebScraper
2. parsers.py - HTML-parsers för olika sidor
3. tests/test_scraper.py - Enhetstester med mocking
4. requirements.txt - Dependencies

Scrapern ska kunna:
- Hämta HTML från URL
- Parsa ut specifika element (titlar, länkar)
- Hantera fel gracefully
- Rate limiting""",
        validators=[
            {"type": "file_exists", "filename": "scraper.py"},
            {"type": "file_exists", "filename": "parsers.py"},
            {"type": "file_exists", "filename": "requirements.txt"},
            {"type": "python_syntax", "filename": "scraper.py"},
            {"type": "python_syntax", "filename": "parsers.py"},
            {"type": "class_exists", "filename": "scraper.py", "class_name": "WebScraper"},
            {"type": "file_contains", "filename": "scraper.py", "pattern": r"requests|httpx|aiohttp"},
            {"type": "file_contains", "filename": "parsers.py", "pattern": r"BeautifulSoup|lxml|selectolax"},
        ],
        difficulty="hard",
        points=35,
    ),
]


# ===========================================
# Eval Runner
# ===========================================

class EvalRunner:
    """Runs evaluation tests against AgentFarm."""

    def __init__(self, agentfarm_path: str = None):
        self.agentfarm_path = Path(agentfarm_path or Path(__file__).parent.parent)
        self.results_dir = self.agentfarm_path / "evals" / "results"
        self.results_dir.mkdir(exist_ok=True)

    async def run_test(self, test: TestCase) -> TestResult:
        """Run a single test case."""
        start_time = time.time()
        errors = []
        validator_results = []

        # Create temp project directory
        with tempfile.TemporaryDirectory(prefix=f"eval_{test.id}_") as tmpdir:
            project_path = Path(tmpdir)

            try:
                # Run AgentFarm workflow
                await self._run_workflow(test.prompt, project_path)

                # Run validators
                for validator in test.validators:
                    v_type = validator["type"]
                    v_func = VALIDATORS.get(v_type)

                    if not v_func:
                        errors.append(f"Unknown validator: {v_type}")
                        validator_results.append(False)
                        continue

                    # Prepare validator args
                    v_args = {k: v for k, v in validator.items() if k != "type"}

                    try:
                        passed, message = v_func(project_path, **v_args)
                        validator_results.append(passed)
                        if not passed:
                            errors.append(message)
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

        # Calculate score
        if validator_results:
            score = sum(validator_results) / len(validator_results)
        else:
            score = 0.0

        passed = score >= 0.8  # 80% threshold for passing

        return TestResult(
            test_id=test.id,
            passed=passed,
            score=score,
            duration=duration,
            errors=errors,
            details={
                "validators_passed": sum(validator_results),
                "validators_total": len(validator_results),
            }
        )

    async def _run_workflow(self, prompt: str, project_path: Path):
        """Run AgentFarm workflow for a test."""
        from agentfarm.orchestrator import Orchestrator
        from agentfarm.tools.file_tools import FileTools

        # Create orchestrator in multi-provider mode
        orchestrator = Orchestrator(
            provider=None,
            working_dir=str(project_path),
            use_multi_provider=True,
        )

        # Inject file tools
        file_tools = FileTools(str(project_path))
        orchestrator.inject_tools(file_tools=file_tools)

        # Run workflow
        await asyncio.wait_for(
            orchestrator.run_workflow(prompt),
            timeout=300  # 5 minute timeout
        )

    async def run_all(self, category: str = None) -> EvalReport:
        """Run all tests (or filtered by category)."""
        tests = TEST_CASES
        if category:
            tests = [t for t in tests if t.category == category]

        print(f"\n{'='*60}")
        print(f"  AGENTFARM EVALUATION SUITE")
        print(f"{'='*60}")
        print(f"  Tests: {len(tests)}")
        print(f"  Category: {category or 'ALL'}")
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

        # Calculate totals
        passed = sum(1 for r in results if r.passed)
        total_score = sum(r.score * TEST_CASES[i].points
                         for i, r in enumerate(results)
                         if tests[i].id == r.test_id)
        max_score = sum(t.points for t in tests)

        # By category
        by_category = {}
        for cat in [CATEGORY_CODEGEN, CATEGORY_BUGFIX, CATEGORY_REFACTOR, CATEGORY_MULTISTEP]:
            cat_results = [r for r, t in zip(results, tests) if t.category == cat]
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

        # Print summary
        print(f"\n{'='*60}")
        print(f"  RESULTS SUMMARY")
        print(f"{'='*60}")
        print(f"  Passed: {passed}/{len(tests)}")
        print(f"  Score:  {total_score:.1f}/{max_score} ({report.percentage:.1f}%)")
        print(f"  Time:   {total_duration:.1f}s")
        print()
        print("  By Category:")
        for cat, stats in by_category.items():
            print(f"    {cat}: {stats['passed']}/{stats['total']} ({stats['avg_score']:.0%})")
        print(f"{'='*60}\n")

        # Save report
        report_path = self.results_dir / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w") as f:
            json.dump({
                "timestamp": report.timestamp,
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
                    }
                    for r in results
                ],
            }, f, indent=2)

        print(f"  Report saved: {report_path}")

        return report

    def list_tests(self):
        """List all available tests."""
        print(f"\n{'='*60}")
        print(f"  AVAILABLE TESTS")
        print(f"{'='*60}\n")

        for cat in [CATEGORY_CODEGEN, CATEGORY_BUGFIX, CATEGORY_REFACTOR, CATEGORY_MULTISTEP]:
            tests = [t for t in TEST_CASES if t.category == cat]
            if tests:
                print(f"  {cat.upper()}:")
                for t in tests:
                    print(f"    [{t.id}] {t.name} ({t.difficulty}, {t.points}pts)")
                print()


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="AgentFarm Evaluation Suite")
    parser.add_argument("--category", "-c", choices=["codegen", "bugfix", "refactor", "multistep"],
                        help="Run only tests in this category")
    parser.add_argument("--list", "-l", action="store_true", help="List all tests")
    parser.add_argument("--test", "-t", help="Run a specific test by ID")
    args = parser.parse_args()

    runner = EvalRunner()

    if args.list:
        runner.list_tests()
        return

    if args.test:
        test = next((t for t in TEST_CASES if t.id == args.test), None)
        if not test:
            print(f"Test not found: {args.test}")
            return
        asyncio.run(runner.run_test(test))
    else:
        asyncio.run(runner.run_all(category=args.category))


if __name__ == "__main__":
    main()
