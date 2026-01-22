"""Code quality scoring and metrics."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class QualityGrade(Enum):
    """Letter grades for code quality."""

    A = "A"  # 90-100: Excellent
    B = "B"  # 80-89: Good
    C = "C"  # 70-79: Acceptable
    D = "D"  # 60-69: Needs improvement
    F = "F"  # <60: Failing

    @classmethod
    def from_score(cls, score: float) -> "QualityGrade":
        """Convert numeric score to letter grade."""
        if score >= 90:
            return cls.A
        elif score >= 80:
            return cls.B
        elif score >= 70:
            return cls.C
        elif score >= 60:
            return cls.D
        else:
            return cls.F


@dataclass
class QualityMetric:
    """A single quality metric."""

    name: str
    score: float  # 0-100
    weight: float  # Weight in composite score
    details: str = ""
    raw_value: Any = None  # Original value before normalization


@dataclass
class CodeQualityScore:
    """Composite code quality score from multiple metrics.

    Metrics and their default weights:
    - test_score (30%): Test pass rate
    - lint_score (20%): Linter compliance
    - type_score (15%): Type check pass rate
    - coverage_score (25%): Test coverage percentage
    - complexity_score (10%): Code complexity (inverse)

    Example usage:
        quality = CodeQualityScore()

        # Add metrics from verification results
        quality.add_metric("test_score", 95, details="19/20 tests passed")
        quality.add_metric("lint_score", 80, details="5 lint issues")
        quality.add_metric("type_score", 100, details="0 type errors")
        quality.add_metric("coverage_score", 85, details="85% coverage")

        print(f"Quality: {quality.grade.value} ({quality.total_score:.1f})")
    """

    metrics: dict[str, QualityMetric] = field(default_factory=dict)
    custom_weights: dict[str, float] | None = None

    # Default weights for standard metrics
    DEFAULT_WEIGHTS: dict[str, float] = field(default_factory=lambda: {
        "test_score": 30.0,
        "lint_score": 20.0,
        "type_score": 15.0,
        "coverage_score": 25.0,
        "complexity_score": 10.0,
    })

    def __post_init__(self) -> None:
        """Initialize default weights."""
        if not hasattr(self, '_weights'):
            self._weights = self.custom_weights or self.DEFAULT_WEIGHTS.copy()

    def get_weight(self, metric_name: str) -> float:
        """Get weight for a metric."""
        weights = self.custom_weights or self.DEFAULT_WEIGHTS
        return weights.get(metric_name, 10.0)  # Default weight of 10

    def add_metric(
        self,
        name: str,
        score: float,
        weight: float | None = None,
        details: str = "",
        raw_value: Any = None,
    ) -> None:
        """Add or update a quality metric.

        Args:
            name: Metric name (e.g., "test_score")
            score: Score 0-100
            weight: Custom weight (default: from DEFAULT_WEIGHTS)
            details: Human-readable details
            raw_value: Original value before normalization
        """
        if weight is None:
            weight = self.get_weight(name)

        self.metrics[name] = QualityMetric(
            name=name,
            score=max(0.0, min(100.0, score)),  # Clamp to 0-100
            weight=weight,
            details=details,
            raw_value=raw_value,
        )

    def add_test_results(
        self,
        passed: int,
        failed: int,
        skipped: int = 0,
    ) -> None:
        """Add test results as a metric."""
        total = passed + failed
        if total == 0:
            score = 100.0 if failed == 0 else 0.0
        else:
            score = (passed / total) * 100.0

        self.add_metric(
            "test_score",
            score,
            details=f"{passed}/{total} tests passed ({skipped} skipped)",
            raw_value={"passed": passed, "failed": failed, "skipped": skipped},
        )

    def add_lint_results(
        self,
        issues: list[str] | int,
        max_acceptable: int = 10,
    ) -> None:
        """Add linting results as a metric.

        Args:
            issues: List of lint issues or count
            max_acceptable: Issues above this count = 0 score
        """
        issue_count = len(issues) if isinstance(issues, list) else issues

        if issue_count == 0:
            score = 100.0
        elif issue_count >= max_acceptable:
            score = 0.0
        else:
            score = ((max_acceptable - issue_count) / max_acceptable) * 100.0

        self.add_metric(
            "lint_score",
            score,
            details=f"{issue_count} lint issues",
            raw_value=issues,
        )

    def add_type_results(
        self,
        errors: list[str] | int,
        max_acceptable: int = 5,
    ) -> None:
        """Add type check results as a metric."""
        error_count = len(errors) if isinstance(errors, list) else errors

        if error_count == 0:
            score = 100.0
        elif error_count >= max_acceptable:
            score = 0.0
        else:
            score = ((max_acceptable - error_count) / max_acceptable) * 100.0

        self.add_metric(
            "type_score",
            score,
            details=f"{error_count} type errors",
            raw_value=errors,
        )

    def add_coverage(self, percent: float | None) -> None:
        """Add test coverage as a metric."""
        if percent is None:
            # No coverage data - use neutral score
            self.add_metric(
                "coverage_score",
                70.0,  # Neutral score when no data
                details="No coverage data",
                raw_value=None,
            )
        else:
            self.add_metric(
                "coverage_score",
                percent,
                details=f"{percent:.1f}% coverage",
                raw_value=percent,
            )

    @property
    def total_score(self) -> float:
        """Calculate weighted total score (0-100)."""
        if not self.metrics:
            return 0.0

        total_weight = sum(m.weight for m in self.metrics.values())
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(m.score * m.weight for m in self.metrics.values())
        return weighted_sum / total_weight

    @property
    def grade(self) -> QualityGrade:
        """Get letter grade based on total score."""
        return QualityGrade.from_score(self.total_score)

    @property
    def is_passing(self) -> bool:
        """Check if quality is passing (grade D or better)."""
        return self.grade != QualityGrade.F

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of quality metrics."""
        return {
            "total_score": round(self.total_score, 1),
            "grade": self.grade.value,
            "is_passing": self.is_passing,
            "metrics": {
                name: {
                    "score": round(m.score, 1),
                    "weight": m.weight,
                    "details": m.details,
                }
                for name, m in self.metrics.items()
            },
        }

    def get_issues(self) -> list[str]:
        """Get list of quality issues (metrics below 70)."""
        issues = []
        for name, metric in self.metrics.items():
            if metric.score < 70:
                issues.append(f"{name}: {metric.details} (score: {metric.score:.0f})")
        return issues

    def __str__(self) -> str:
        """Human-readable quality summary."""
        return f"Quality: {self.grade.value} ({self.total_score:.1f}/100)"

    @classmethod
    def from_verification_result(cls, result: Any) -> "CodeQualityScore":
        """Create quality score from a VerificationResult.

        Args:
            result: VerificationResult from verifier agent

        Returns:
            CodeQualityScore with metrics from the result
        """
        quality = cls()

        # Add test results
        quality.add_test_results(
            passed=getattr(result, "tests_passed", 0),
            failed=getattr(result, "tests_failed", 0),
            skipped=getattr(result, "tests_skipped", 0),
        )

        # Add lint results
        lint_issues = getattr(result, "lint_issues", [])
        quality.add_lint_results(lint_issues)

        # Add type results
        type_errors = getattr(result, "type_errors", [])
        quality.add_type_results(type_errors)

        # Add coverage
        coverage = getattr(result, "coverage_percent", None)
        quality.add_coverage(coverage)

        return quality
