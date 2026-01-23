"""Evaluation tool handler for MCP integration.

This module provides tools for running and managing the AgentFarm evaluation suite
via the Model Context Protocol (MCP).
"""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import EvalRunResult


class EvalToolHandler:
    """Handler for evaluation-related MCP tools.

    Provides methods to run evaluations, list available tests, and retrieve
    historical results from the AgentFarm evaluation suite.

    Attributes:
        working_dir: The base working directory for the AgentFarm project.
        results_dir: Path to the directory containing evaluation result files.
    """

    def __init__(self, working_dir: str) -> None:
        """Initialize the evaluation tool handler.

        Args:
            working_dir: The base working directory for the AgentFarm project.
                This should be the root of the project containing the evals/ directory.
        """
        self.working_dir = working_dir
        self.results_dir = Path(working_dir) / "evals" / "results"

    async def run_eval(self, category: str | None = None, quick: bool = False) -> str:
        """Run the evaluation suite and return results as JSON.

        Executes the AgentFarm evaluation suite, optionally filtered by category.
        Results are returned as a JSON-serialized EvalRunResult.

        Args:
            category: Optional category to filter tests (e.g., 'codegen', 'bugfix',
                'refactor', 'multistep'). If None, runs all tests.
            quick: If True, runs a quick sanity check instead of full evaluation.
                Currently not implemented - reserved for future use.

        Returns:
            JSON string containing the evaluation results with fields:
            - success: Whether any tests passed
            - tests_run: Total number of tests executed
            - tests_passed: Number of passing tests
            - tests_failed: Number of failing tests
            - total_score: Sum of points earned
            - max_score: Maximum possible points
            - percentage: Score as a percentage
            - duration_seconds: Total execution time
            - by_category: Breakdown of results by category
        """
        from evals.suite import EvalRunner

        runner = EvalRunner(self.working_dir)
        report = await runner.run_all(category=category)
        return json.dumps(
            EvalRunResult(
                success=report.passed > 0,
                tests_run=report.total_tests,
                tests_passed=report.passed,
                tests_failed=report.failed,
                total_score=report.total_score,
                max_score=report.max_score,
                percentage=report.percentage,
                duration_seconds=report.duration,
                by_category=report.by_category,
            ).model_dump()
        )

    def list_evals(self) -> str:
        """List all available evaluation tests.

        Returns metadata about each test case in the evaluation suite,
        including ID, name, category, difficulty, and point value.

        Returns:
            JSON string containing:
            - tests: List of test metadata objects with fields:
                - id: Unique test identifier (e.g., 'codegen-001')
                - name: Human-readable test name
                - category: Test category (codegen, bugfix, refactor, multistep)
                - difficulty: Difficulty level (easy, medium, hard)
                - points: Point value for the test
            - count: Total number of tests available
        """
        from evals.suite import TEST_CASES

        tests = [
            {
                "id": t.id,
                "name": t.name,
                "category": t.category,
                "difficulty": t.difficulty,
                "points": t.points,
            }
            for t in TEST_CASES
        ]
        return json.dumps({"tests": tests, "count": len(tests)})

    async def run_single_eval(self, test_id: str, verbose: bool = False) -> str:
        """Run a single evaluation test by ID.

        Executes a specific test case and returns detailed results.
        Useful for debugging or re-running individual failing tests.

        Args:
            test_id: The unique identifier of the test to run (e.g., 'codegen-001').
            verbose: If True, includes all error messages in the response.
                If False, limits errors to the first 3 for brevity.

        Returns:
            JSON string containing:
            - test_id: The ID of the test that was run
            - passed: Whether the test passed
            - score: Points earned (0 if failed, full points if passed)
            - duration: Execution time in seconds
            - errors: List of error messages (truncated if not verbose)

            If the test ID is not found, returns:
            - error: Error message indicating the test was not found
        """
        from evals.suite import EvalRunner, TEST_CASES

        test = next((t for t in TEST_CASES if t.id == test_id), None)
        if not test:
            return json.dumps({"error": f"Test not found: {test_id}"})
        runner = EvalRunner(self.working_dir)
        result = await runner.run_test(test)
        return json.dumps(
            {
                "test_id": result.test_id,
                "passed": result.passed,
                "score": result.score,
                "duration": result.duration,
                "errors": result.errors if verbose else result.errors[:3],
            }
        )

    def get_eval_results(self, limit: int = 10) -> str:
        """Retrieve historical evaluation results.

        Reads saved evaluation reports from the results directory and returns
        summary information about recent runs. Results are sorted by filename
        in reverse order (most recent first).

        Args:
            limit: Maximum number of results to return. Defaults to 10.

        Returns:
            JSON string containing:
            - results: List of result summaries with fields:
                - file: Filename of the result file
                - timestamp: When the evaluation was run
                - passed: Number of tests that passed
                - failed: Number of tests that failed
                - percentage: Overall score percentage
            - count: Number of results returned

            If no results exist, returns empty results list with count 0.
        """
        if not self.results_dir.exists():
            return json.dumps({"results": [], "count": 0})
        results = sorted(self.results_dir.glob("eval_*.json"), reverse=True)[:limit]
        reports = []
        for r in results:
            try:
                data = json.loads(r.read_text())
                reports.append(
                    {
                        "file": r.name,
                        "timestamp": data.get("timestamp"),
                        "passed": data.get("passed"),
                        "failed": data.get("failed"),
                        "percentage": data.get("percentage"),
                    }
                )
            except Exception:
                continue
        return json.dumps({"results": reports, "count": len(reports)})
