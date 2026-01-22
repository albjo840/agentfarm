"""Smart retry logic with error categorization."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorCategory(Enum):
    """Categories of errors for retry decisions."""

    TRANSIENT = "transient"  # Timeout, rate limit, network - retry with backoff
    FLAKY = "flaky"  # Intermittent failures - retry with jitter
    FIXABLE = "fixable"  # Can be fixed by adjusting approach - limited retry
    PERMANENT = "permanent"  # Logic error, invalid input - no retry


@dataclass
class RetryConfig:
    """Configuration for a specific error category."""

    max_retries: int
    base_delay: float  # seconds
    max_delay: float  # seconds
    exponential_base: float = 2.0
    jitter: bool = False


# Default retry configurations per error category
DEFAULT_RETRY_CONFIGS: dict[ErrorCategory, RetryConfig] = {
    ErrorCategory.TRANSIENT: RetryConfig(
        max_retries=3,
        base_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
    ),
    ErrorCategory.FLAKY: RetryConfig(
        max_retries=2,
        base_delay=0.5,
        max_delay=5.0,
        exponential_base=1.5,
        jitter=True,
    ),
    ErrorCategory.FIXABLE: RetryConfig(
        max_retries=1,
        base_delay=0.0,
        max_delay=0.0,
        exponential_base=1.0,
        jitter=False,
    ),
    ErrorCategory.PERMANENT: RetryConfig(
        max_retries=0,
        base_delay=0.0,
        max_delay=0.0,
        exponential_base=1.0,
        jitter=False,
    ),
}


@dataclass
class RetryResult:
    """Result of a retry operation."""

    success: bool
    result: Any | None = None
    error: Exception | None = None
    attempts: int = 1
    total_delay: float = 0.0
    error_categories: list[ErrorCategory] = field(default_factory=list)


class SmartRetryManager:
    """Manages retries with error categorization and adaptive delays.

    Example usage:
        retry_manager = SmartRetryManager()

        async def flaky_operation():
            # ... some operation that might fail
            pass

        result = await retry_manager.execute_with_retry(
            operation=flaky_operation,
            categorize_error=lambda e: ErrorCategory.TRANSIENT if "timeout" in str(e) else ErrorCategory.PERMANENT,
        )
    """

    def __init__(
        self,
        configs: dict[ErrorCategory, RetryConfig] | None = None,
    ) -> None:
        """Initialize with optional custom retry configs."""
        self.configs = configs or DEFAULT_RETRY_CONFIGS.copy()
        self._stats: dict[str, int] = {
            "total_attempts": 0,
            "successful_retries": 0,
            "failed_retries": 0,
            "permanent_failures": 0,
        }

    def categorize_error_default(self, error: Exception) -> ErrorCategory:
        """Default error categorization based on error message/type."""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()

        # Transient errors (network, rate limits, timeouts)
        transient_patterns = [
            "timeout",
            "timed out",
            "rate limit",
            "429",
            "503",
            "502",
            "connection refused",
            "connection reset",
            "network",
            "temporary",
            "retry",
            "overloaded",
        ]
        if any(pattern in error_str or pattern in error_type for pattern in transient_patterns):
            return ErrorCategory.TRANSIENT

        # Flaky errors (intermittent, non-deterministic)
        flaky_patterns = [
            "intermittent",
            "flaky",
            "unstable",
            "race condition",
            "deadlock",
        ]
        if any(pattern in error_str for pattern in flaky_patterns):
            return ErrorCategory.FLAKY

        # Fixable errors (can be resolved by changing approach)
        fixable_patterns = [
            "not found",
            "missing",
            "invalid path",
            "permission denied",
        ]
        if any(pattern in error_str for pattern in fixable_patterns):
            return ErrorCategory.FIXABLE

        # Default to permanent
        return ErrorCategory.PERMANENT

    def calculate_delay(
        self,
        category: ErrorCategory,
        attempt: int,
    ) -> float:
        """Calculate delay for a given error category and attempt number."""
        config = self.configs.get(category, DEFAULT_RETRY_CONFIGS[ErrorCategory.PERMANENT])

        if config.max_retries == 0:
            return 0.0

        # Exponential backoff
        delay = config.base_delay * (config.exponential_base ** (attempt - 1))
        delay = min(delay, config.max_delay)

        # Add jitter if configured (prevents thundering herd)
        if config.jitter:
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
            delay = max(0.0, delay)

        return delay

    def should_retry(
        self,
        category: ErrorCategory,
        attempt: int,
    ) -> bool:
        """Check if we should retry for given category and attempt."""
        config = self.configs.get(category, DEFAULT_RETRY_CONFIGS[ErrorCategory.PERMANENT])
        return attempt <= config.max_retries

    async def execute_with_retry(
        self,
        operation: Callable[[], Awaitable[T]],
        categorize_error: Callable[[Exception], ErrorCategory] | None = None,
        on_retry: Callable[[int, ErrorCategory, float], Awaitable[None]] | None = None,
    ) -> RetryResult:
        """Execute an operation with smart retry logic.

        Args:
            operation: Async function to execute
            categorize_error: Function to categorize exceptions (default: built-in)
            on_retry: Optional callback when retrying (attempt, category, delay)

        Returns:
            RetryResult with success status and result/error
        """
        categorize = categorize_error or self.categorize_error_default

        attempt = 0
        total_delay = 0.0
        error_categories: list[ErrorCategory] = []
        last_error: Exception | None = None

        while True:
            attempt += 1
            self._stats["total_attempts"] += 1

            try:
                result = await operation()
                if attempt > 1:
                    self._stats["successful_retries"] += 1
                    logger.info("Operation succeeded after %d attempts", attempt)
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempt,
                    total_delay=total_delay,
                    error_categories=error_categories,
                )

            except Exception as e:
                last_error = e
                category = categorize(e)
                error_categories.append(category)

                logger.warning(
                    "Attempt %d failed with %s error: %s",
                    attempt,
                    category.value,
                    str(e)[:100],
                )

                if not self.should_retry(category, attempt):
                    if category == ErrorCategory.PERMANENT:
                        self._stats["permanent_failures"] += 1
                    else:
                        self._stats["failed_retries"] += 1
                    break

                delay = self.calculate_delay(category, attempt)
                total_delay += delay

                if on_retry:
                    await on_retry(attempt, category, delay)

                if delay > 0:
                    logger.info(
                        "Retrying in %.2f seconds (attempt %d, category=%s)",
                        delay,
                        attempt + 1,
                        category.value,
                    )
                    await asyncio.sleep(delay)

        return RetryResult(
            success=False,
            error=last_error,
            attempts=attempt,
            total_delay=total_delay,
            error_categories=error_categories,
        )

    def get_stats(self) -> dict[str, int]:
        """Get retry statistics."""
        return self._stats.copy()

    def reset_stats(self) -> None:
        """Reset retry statistics."""
        self._stats = {
            "total_attempts": 0,
            "successful_retries": 0,
            "failed_retries": 0,
            "permanent_failures": 0,
        }
