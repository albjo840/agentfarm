"""Test result aggregation and flaky test detection."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TestRun:
    """Record of a single test execution."""

    test_name: str
    passed: bool
    timestamp: float
    duration_ms: float | None = None
    error_message: str | None = None
    run_id: str | None = None  # Links to workflow run


@dataclass
class TestHistory:
    """Historical data for a single test."""

    test_name: str
    runs: list[TestRun] = field(default_factory=list)
    max_history: int = 20  # Keep last N runs

    def add_run(self, run: TestRun) -> None:
        """Add a test run to history."""
        self.runs.append(run)
        # Trim to max history
        if len(self.runs) > self.max_history:
            self.runs = self.runs[-self.max_history:]

    @property
    def total_runs(self) -> int:
        """Total number of recorded runs."""
        return len(self.runs)

    @property
    def pass_count(self) -> int:
        """Number of passing runs."""
        return sum(1 for r in self.runs if r.passed)

    @property
    def fail_count(self) -> int:
        """Number of failing runs."""
        return sum(1 for r in self.runs if not r.passed)

    @property
    def pass_rate(self) -> float:
        """Pass rate as percentage (0-100)."""
        if not self.runs:
            return 0.0
        return (self.pass_count / len(self.runs)) * 100.0

    @property
    def is_flaky(self) -> bool:
        """Check if test is flaky (20-80% pass rate with 3+ runs)."""
        if self.total_runs < 3:
            return False
        return 20.0 <= self.pass_rate <= 80.0

    @property
    def is_consistently_failing(self) -> bool:
        """Check if test consistently fails (0% pass rate, 3+ runs)."""
        if self.total_runs < 3:
            return False
        return self.pass_rate == 0.0

    @property
    def is_consistently_passing(self) -> bool:
        """Check if test consistently passes (100% pass rate, 3+ runs)."""
        if self.total_runs < 3:
            return False
        return self.pass_rate == 100.0

    @property
    def last_run(self) -> TestRun | None:
        """Get the most recent run."""
        return self.runs[-1] if self.runs else None

    @property
    def streak(self) -> tuple[str, int]:
        """Get current streak (pass/fail) and count."""
        if not self.runs:
            return ("none", 0)

        current_status = self.runs[-1].passed
        count = 0
        for run in reversed(self.runs):
            if run.passed == current_status:
                count += 1
            else:
                break

        return ("pass" if current_status else "fail", count)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "test_name": self.test_name,
            "total_runs": self.total_runs,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "pass_rate": round(self.pass_rate, 1),
            "is_flaky": self.is_flaky,
            "is_consistently_failing": self.is_consistently_failing,
            "streak": self.streak,
            "runs": [
                {
                    "passed": r.passed,
                    "timestamp": r.timestamp,
                    "duration_ms": r.duration_ms,
                    "error_message": r.error_message[:100] if r.error_message else None,
                }
                for r in self.runs[-5:]  # Only include last 5 runs in dict
            ],
        }


class TestResultAggregator:
    """Aggregates test results across multiple runs to identify patterns.

    Example usage:
        aggregator = TestResultAggregator(storage_path=".agentfarm/test_history.json")

        # Record test results
        aggregator.record_run("test_login", passed=True)
        aggregator.record_run("test_checkout", passed=False, error="Timeout")

        # Analyze patterns
        flaky_tests = aggregator.get_flaky_tests()
        failing_tests = aggregator.get_consistently_failing_tests()

        # Get report
        report = aggregator.get_report()
    """

    def __init__(
        self,
        storage_path: str | Path | None = None,
        max_history_per_test: int = 20,
    ) -> None:
        """Initialize the aggregator.

        Args:
            storage_path: Path to persist test history (optional)
            max_history_per_test: Maximum runs to keep per test
        """
        self.storage_path = Path(storage_path) if storage_path else None
        self.max_history = max_history_per_test
        self._tests: dict[str, TestHistory] = {}
        self._current_run_id: str | None = None

        # Load existing history if available
        if self.storage_path and self.storage_path.exists():
            self._load_history()

    def _load_history(self) -> None:
        """Load test history from storage."""
        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)

            for test_name, test_data in data.get("tests", {}).items():
                history = TestHistory(
                    test_name=test_name,
                    max_history=self.max_history,
                )
                for run_data in test_data.get("runs", []):
                    history.add_run(TestRun(
                        test_name=test_name,
                        passed=run_data["passed"],
                        timestamp=run_data["timestamp"],
                        duration_ms=run_data.get("duration_ms"),
                        error_message=run_data.get("error_message"),
                        run_id=run_data.get("run_id"),
                    ))
                self._tests[test_name] = history

            logger.info("Loaded test history for %d tests", len(self._tests))
        except Exception as e:
            logger.warning("Failed to load test history: %s", e)

    def _save_history(self) -> None:
        """Save test history to storage."""
        if not self.storage_path:
            return

        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "tests": {},
                "last_updated": time.time(),
            }

            for test_name, history in self._tests.items():
                data["tests"][test_name] = {
                    "runs": [
                        {
                            "passed": r.passed,
                            "timestamp": r.timestamp,
                            "duration_ms": r.duration_ms,
                            "error_message": r.error_message,
                            "run_id": r.run_id,
                        }
                        for r in history.runs
                    ]
                }

            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.warning("Failed to save test history: %s", e)

    def start_run(self, run_id: str | None = None) -> str:
        """Start a new test run.

        Args:
            run_id: Optional run ID (generated if not provided)

        Returns:
            The run ID
        """
        self._current_run_id = run_id or f"run_{int(time.time())}"
        return self._current_run_id

    def end_run(self) -> None:
        """End the current test run and save history."""
        self._current_run_id = None
        self._save_history()

    def record_run(
        self,
        test_name: str,
        passed: bool,
        duration_ms: float | None = None,
        error_message: str | None = None,
    ) -> None:
        """Record a single test run.

        Args:
            test_name: Name of the test
            passed: Whether the test passed
            duration_ms: Test duration in milliseconds
            error_message: Error message if failed
        """
        if test_name not in self._tests:
            self._tests[test_name] = TestHistory(
                test_name=test_name,
                max_history=self.max_history,
            )

        self._tests[test_name].add_run(TestRun(
            test_name=test_name,
            passed=passed,
            timestamp=time.time(),
            duration_ms=duration_ms,
            error_message=error_message,
            run_id=self._current_run_id,
        ))

    def record_batch(
        self,
        results: list[dict[str, Any]],
    ) -> None:
        """Record multiple test results at once.

        Args:
            results: List of dicts with keys: name, passed, duration_ms, error
        """
        for result in results:
            self.record_run(
                test_name=result["name"],
                passed=result["passed"],
                duration_ms=result.get("duration_ms"),
                error_message=result.get("error"),
            )

    def get_test_history(self, test_name: str) -> TestHistory | None:
        """Get history for a specific test."""
        return self._tests.get(test_name)

    def get_flaky_tests(self) -> list[TestHistory]:
        """Get all flaky tests (20-80% pass rate)."""
        return [h for h in self._tests.values() if h.is_flaky]

    def get_consistently_failing_tests(self) -> list[TestHistory]:
        """Get tests that consistently fail."""
        return [h for h in self._tests.values() if h.is_consistently_failing]

    def get_consistently_passing_tests(self) -> list[TestHistory]:
        """Get tests that consistently pass."""
        return [h for h in self._tests.values() if h.is_consistently_passing]

    def get_recent_failures(self, within_runs: int = 3) -> list[TestHistory]:
        """Get tests that failed in recent runs."""
        failures = []
        for history in self._tests.values():
            recent = history.runs[-within_runs:] if history.runs else []
            if any(not r.passed for r in recent):
                failures.append(history)
        return failures

    def get_report(self) -> dict[str, Any]:
        """Generate a summary report of test results.

        Returns:
            Dict with test statistics and patterns
        """
        total_tests = len(self._tests)
        flaky = self.get_flaky_tests()
        failing = self.get_consistently_failing_tests()
        passing = self.get_consistently_passing_tests()

        # Calculate overall pass rate from most recent runs
        recent_passed = 0
        recent_total = 0
        for history in self._tests.values():
            if history.last_run:
                recent_total += 1
                if history.last_run.passed:
                    recent_passed += 1

        return {
            "total_tests": total_tests,
            "recent_pass_rate": (
                round((recent_passed / recent_total) * 100, 1)
                if recent_total > 0 else 0.0
            ),
            "flaky_tests": {
                "count": len(flaky),
                "tests": [h.test_name for h in flaky],
            },
            "consistently_failing": {
                "count": len(failing),
                "tests": [h.test_name for h in failing],
            },
            "consistently_passing": {
                "count": len(passing),
                "tests": [h.test_name for h in passing[:10]],  # Limit output
            },
            "tests": {
                name: history.to_dict()
                for name, history in sorted(
                    self._tests.items(),
                    key=lambda x: x[1].pass_rate,
                )[:20]  # Show worst 20
            },
        }

    def get_recommendations(self) -> list[str]:
        """Get recommendations based on test patterns.

        Returns:
            List of actionable recommendations
        """
        recommendations = []

        flaky = self.get_flaky_tests()
        if flaky:
            recommendations.append(
                f"Fix {len(flaky)} flaky tests: {', '.join(h.test_name for h in flaky[:5])}"
            )

        failing = self.get_consistently_failing_tests()
        if failing:
            recommendations.append(
                f"Investigate {len(failing)} consistently failing tests: "
                f"{', '.join(h.test_name for h in failing[:5])}"
            )

        # Check for slow tests
        slow_tests = []
        for history in self._tests.values():
            if history.last_run and history.last_run.duration_ms:
                if history.last_run.duration_ms > 5000:  # > 5 seconds
                    slow_tests.append(history.test_name)

        if slow_tests:
            recommendations.append(
                f"Optimize {len(slow_tests)} slow tests: {', '.join(slow_tests[:5])}"
            )

        return recommendations
