"""Performance Tracker - LLM throughput and latency metrics.

Tracks:
- Tokens per second (input/output)
- Request latency (p50, p95, p99)
- Per-model and per-agent statistics
- Historical trends

Integrates with LLMRouter events for automatic tracking.
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class LLMMetrics:
    """Metrics for a single LLM request."""

    model: str
    agent: str | None = None
    task_type: str | None = None

    # Timing
    start_time: float = 0.0
    end_time: float = 0.0
    latency_ms: float = 0.0

    # Tokens
    input_tokens: int = 0
    output_tokens: int = 0

    # Calculated
    tokens_per_second: float = 0.0

    success: bool = True
    error: str | None = None

    def finalize(self) -> None:
        """Calculate derived metrics after request completes."""
        self.end_time = time.time()
        self.latency_ms = (self.end_time - self.start_time) * 1000

        if self.latency_ms > 0:
            # Output tokens per second (generation speed)
            self.tokens_per_second = (self.output_tokens / self.latency_ms) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "agent": self.agent,
            "task_type": self.task_type,
            "latency_ms": round(self.latency_ms, 1),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "tokens_per_second": round(self.tokens_per_second, 1),
            "success": self.success,
            "error": self.error,
        }


@dataclass
class ModelStats:
    """Aggregated statistics for a model."""

    model: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    total_input_tokens: int = 0
    total_output_tokens: int = 0

    latencies: list[float] = field(default_factory=list)
    tokens_per_second: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)

    @property
    def p50_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.median(self.latencies)

    @property
    def p95_latency_ms(self) -> float:
        if len(self.latencies) < 2:
            return self.avg_latency_ms
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def p99_latency_ms(self) -> float:
        if len(self.latencies) < 2:
            return self.avg_latency_ms
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def avg_tokens_per_second(self) -> float:
        if not self.tokens_per_second:
            return 0.0
        return statistics.mean(self.tokens_per_second)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "total_requests": self.total_requests,
            "success_rate": round(self.success_rate, 1),
            "tokens": {
                "input": self.total_input_tokens,
                "output": self.total_output_tokens,
                "total": self.total_input_tokens + self.total_output_tokens,
            },
            "latency_ms": {
                "avg": round(self.avg_latency_ms, 1),
                "p50": round(self.p50_latency_ms, 1),
                "p95": round(self.p95_latency_ms, 1),
                "p99": round(self.p99_latency_ms, 1),
            },
            "tokens_per_second": round(self.avg_tokens_per_second, 1),
        }


class PerformanceTracker:
    """Track LLM performance metrics across models and agents.

    Usage:
        tracker = PerformanceTracker()

        # Start tracking a request
        metrics = tracker.start_request(model="qwen2.5-coder:7b", agent="executor")

        # ... make LLM call ...

        # Record completion
        tracker.complete_request(metrics, input_tokens=100, output_tokens=50)

        # Get statistics
        stats = tracker.get_stats()
        print(f"Avg tokens/sec: {stats['overall']['avg_tokens_per_second']}")

    Integration with EventBus:
        bus.subscribe(EventType.LLM_REQUEST, tracker.on_llm_request)
        bus.subscribe(EventType.LLM_RESPONSE, tracker.on_llm_response)
    """

    DEFAULT_HISTORY_SIZE = 1000
    DEFAULT_RETENTION_HOURS = 24

    def __init__(
        self,
        history_size: int = DEFAULT_HISTORY_SIZE,
        retention_hours: int = DEFAULT_RETENTION_HOURS,
    ) -> None:
        """Initialize performance tracker.

        Args:
            history_size: Max number of metrics to keep in memory
            retention_hours: How long to keep metrics for trends
        """
        self.history_size = history_size
        self.retention_hours = retention_hours

        # Recent metrics (rolling window)
        self._metrics: deque[LLMMetrics] = deque(maxlen=history_size)

        # Per-model statistics
        self._model_stats: dict[str, ModelStats] = {}

        # Per-agent statistics
        self._agent_stats: dict[str, ModelStats] = {}

        # Active requests (for tracking in-flight)
        self._active_requests: dict[str, LLMMetrics] = {}

    def start_request(
        self,
        model: str,
        agent: str | None = None,
        task_type: str | None = None,
        request_id: str | None = None,
    ) -> LLMMetrics:
        """Start tracking a new LLM request.

        Args:
            model: Model name
            agent: Agent making the request
            task_type: Type of task (code_generation, etc.)
            request_id: Optional ID for tracking

        Returns:
            LLMMetrics to pass to complete_request
        """
        metrics = LLMMetrics(
            model=model,
            agent=agent,
            task_type=task_type,
            start_time=time.time(),
        )

        if request_id:
            self._active_requests[request_id] = metrics

        return metrics

    def complete_request(
        self,
        metrics: LLMMetrics,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Complete tracking for a request.

        Args:
            metrics: Metrics from start_request
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            success: Whether request succeeded
            error: Error message if failed
        """
        metrics.input_tokens = input_tokens
        metrics.output_tokens = output_tokens
        metrics.success = success
        metrics.error = error
        metrics.finalize()

        self._metrics.append(metrics)
        self._update_stats(metrics)

    def complete_by_id(
        self,
        request_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> LLMMetrics | None:
        """Complete a request by ID.

        Args:
            request_id: ID from start_request

        Returns:
            Completed metrics or None if not found
        """
        metrics = self._active_requests.pop(request_id, None)
        if metrics:
            self.complete_request(metrics, input_tokens, output_tokens, success, error)
        return metrics

    def _update_stats(self, metrics: LLMMetrics) -> None:
        """Update aggregated statistics."""
        # Update model stats
        if metrics.model not in self._model_stats:
            self._model_stats[metrics.model] = ModelStats(model=metrics.model)

        model_stat = self._model_stats[metrics.model]
        model_stat.total_requests += 1

        if metrics.success:
            model_stat.successful_requests += 1
        else:
            model_stat.failed_requests += 1

        model_stat.total_input_tokens += metrics.input_tokens
        model_stat.total_output_tokens += metrics.output_tokens
        model_stat.latencies.append(metrics.latency_ms)
        if metrics.tokens_per_second > 0:
            model_stat.tokens_per_second.append(metrics.tokens_per_second)

        # Keep stats bounded
        if len(model_stat.latencies) > self.history_size:
            model_stat.latencies = model_stat.latencies[-self.history_size:]
            model_stat.tokens_per_second = model_stat.tokens_per_second[-self.history_size:]

        # Update agent stats
        if metrics.agent:
            if metrics.agent not in self._agent_stats:
                self._agent_stats[metrics.agent] = ModelStats(model=metrics.agent)

            agent_stat = self._agent_stats[metrics.agent]
            agent_stat.total_requests += 1
            if metrics.success:
                agent_stat.successful_requests += 1
            else:
                agent_stat.failed_requests += 1
            agent_stat.total_input_tokens += metrics.input_tokens
            agent_stat.total_output_tokens += metrics.output_tokens
            agent_stat.latencies.append(metrics.latency_ms)
            if metrics.tokens_per_second > 0:
                agent_stat.tokens_per_second.append(metrics.tokens_per_second)

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive performance statistics."""
        # Calculate overall stats
        all_latencies = [m.latency_ms for m in self._metrics if m.success]
        all_tps = [m.tokens_per_second for m in self._metrics if m.success and m.tokens_per_second > 0]

        total_requests = len(self._metrics)
        successful = sum(1 for m in self._metrics if m.success)

        overall = {
            "total_requests": total_requests,
            "successful_requests": successful,
            "success_rate": round((successful / total_requests * 100) if total_requests > 0 else 0, 1),
            "avg_latency_ms": round(statistics.mean(all_latencies), 1) if all_latencies else 0,
            "avg_tokens_per_second": round(statistics.mean(all_tps), 1) if all_tps else 0,
            "active_requests": len(self._active_requests),
        }

        return {
            "overall": overall,
            "by_model": {k: v.to_dict() for k, v in self._model_stats.items()},
            "by_agent": {k: v.to_dict() for k, v in self._agent_stats.items()},
            "recent": [m.to_dict() for m in list(self._metrics)[-10:]],
        }

    def get_model_stats(self, model: str) -> ModelStats | None:
        """Get statistics for a specific model."""
        return self._model_stats.get(model)

    def get_recent_metrics(self, limit: int = 10) -> list[LLMMetrics]:
        """Get most recent metrics."""
        return list(self._metrics)[-limit:]

    def clear(self) -> None:
        """Clear all tracked metrics."""
        self._metrics.clear()
        self._model_stats.clear()
        self._agent_stats.clear()
        self._active_requests.clear()

    # Event handlers for integration with EventBus
    async def on_llm_request(self, event: Any) -> None:
        """Handle LLM_REQUEST event from EventBus."""
        data = event.data if hasattr(event, "data") else event

        request_id = data.get("request_id", str(time.time()))
        self.start_request(
            model=data.get("model", "unknown"),
            agent=data.get("agent"),
            task_type=data.get("task_type"),
            request_id=request_id,
        )

    async def on_llm_response(self, event: Any) -> None:
        """Handle LLM_RESPONSE event from EventBus."""
        data = event.data if hasattr(event, "data") else event

        request_id = data.get("request_id")
        if request_id:
            self.complete_by_id(
                request_id=request_id,
                input_tokens=data.get("input_tokens", 0),
                output_tokens=data.get("output_tokens", 0),
                success=data.get("success", True),
                error=data.get("error"),
            )
