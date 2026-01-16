"""LLM Router for multi-model orchestration.

Routes requests to optimal LLM based on task type, load, and availability.
Supports your local Ollama models:
- qwen2.5-coder:7b  - Fast code generation
- nemotron-mini     - Lightweight, fast responses
- qwen3:14b         - Complex reasoning
- mistral-nemo      - Balanced, good Swedish
- gemma2:9b         - Factual, Google-quality
- phi4              - Code + math

Features:
- Task-based routing (code → qwen-coder, reasoning → qwen3)
- Health checking and fallback
- Load balancing across models
- Event bus integration for monitoring
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from agentfarm.events import EventBus, Event
    from agentfarm.providers.base import CompletionResponse

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Types of tasks for routing decisions."""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    PLANNING = "planning"
    REASONING = "reasoning"
    VERIFICATION = "verification"
    SIMPLE_RESPONSE = "simple_response"
    TRANSLATION = "translation"
    MATH = "math"
    GENERAL = "general"


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    name: str
    ollama_name: str  # Name in Ollama (e.g., "qwen2.5-coder:7b")
    task_types: list[TaskType]  # Tasks this model is good at
    priority: int = 1  # Higher = preferred (1-10)
    max_concurrent: int = 2  # Max concurrent requests
    timeout: float = 120.0  # Request timeout
    context_length: int = 8192  # Max context window


@dataclass
class ModelState:
    """Runtime state for a model."""
    config: ModelConfig
    healthy: bool = True
    current_load: int = 0
    total_requests: int = 0
    total_errors: int = 0
    avg_latency_ms: float = 0.0
    last_check: float = field(default_factory=time.time)
    _latencies: list[float] = field(default_factory=list)

    def record_request(self, latency_ms: float, success: bool) -> None:
        """Record a completed request."""
        self.total_requests += 1
        if not success:
            self.total_errors += 1

        self._latencies.append(latency_ms)
        if len(self._latencies) > 100:
            self._latencies.pop(0)
        self.avg_latency_ms = sum(self._latencies) / len(self._latencies)

    @property
    def error_rate(self) -> float:
        """Get error rate (0.0-1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.total_errors / self.total_requests

    @property
    def available_capacity(self) -> int:
        """Get available request slots."""
        return max(0, self.config.max_concurrent - self.current_load)

    @property
    def score(self) -> float:
        """Calculate routing score (higher = better choice)."""
        if not self.healthy or self.available_capacity == 0:
            return 0.0

        # Base score from priority
        score = self.config.priority * 10.0

        # Penalize high load
        load_factor = 1.0 - (self.current_load / self.config.max_concurrent)
        score *= load_factor

        # Penalize high latency
        if self.avg_latency_ms > 0:
            latency_factor = min(1.0, 5000 / self.avg_latency_ms)  # 5s = 1.0
            score *= latency_factor

        # Penalize errors
        score *= (1.0 - self.error_rate)

        return score


# Default model configurations for your setup
DEFAULT_MODELS = [
    ModelConfig(
        name="qwen-coder",
        ollama_name="qwen2.5-coder:7b",
        task_types=[TaskType.CODE_GENERATION, TaskType.CODE_REVIEW],
        priority=9,
        max_concurrent=3,
    ),
    ModelConfig(
        name="qwen3",
        ollama_name="qwen3:14b",
        task_types=[TaskType.REASONING, TaskType.PLANNING],
        priority=8,
        max_concurrent=2,
    ),
    ModelConfig(
        name="phi4",
        ollama_name="phi4",
        task_types=[TaskType.CODE_GENERATION, TaskType.MATH, TaskType.REASONING],
        priority=7,
        max_concurrent=2,
    ),
    ModelConfig(
        name="gemma2",
        ollama_name="gemma2:9b",
        task_types=[TaskType.VERIFICATION, TaskType.GENERAL],
        priority=6,
        max_concurrent=2,
    ),
    ModelConfig(
        name="mistral-nemo",
        ollama_name="mistral-nemo",
        task_types=[TaskType.GENERAL, TaskType.TRANSLATION, TaskType.PLANNING],
        priority=6,
        max_concurrent=2,
    ),
    ModelConfig(
        name="nemotron-mini",
        ollama_name="nemotron-mini",
        task_types=[TaskType.SIMPLE_RESPONSE, TaskType.GENERAL],
        priority=5,
        max_concurrent=4,  # Fast, can handle more
    ),
]


class LLMRouter:
    """Routes LLM requests to optimal models.

    Usage:
        router = LLMRouter(ollama_base_url="http://localhost:11434")
        await router.initialize()  # Check model health

        # Route a code generation request
        response = await router.complete(
            messages=[{"role": "user", "content": "Write a function..."}],
            task_type=TaskType.CODE_GENERATION,
        )
    """

    def __init__(
        self,
        models: list[ModelConfig] | None = None,
        ollama_base_url: str = "http://localhost:11434",
        event_bus: EventBus | None = None,
    ):
        self.models = models or DEFAULT_MODELS
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.event_bus = event_bus

        # Initialize model states
        self._states: dict[str, ModelState] = {
            m.name: ModelState(config=m) for m in self.models
        }

        self._client = httpx.AsyncClient(timeout=120.0)
        self._initialized = False

    async def initialize(self) -> dict[str, bool]:
        """Check health of all models and return availability.

        Returns:
            Dict mapping model name to availability
        """
        results = {}

        for model in self.models:
            healthy = await self._check_model_health(model)
            self._states[model.name].healthy = healthy
            results[model.name] = healthy
            logger.info(
                "Model %s (%s): %s",
                model.name,
                model.ollama_name,
                "available" if healthy else "unavailable",
            )

        self._initialized = True
        return results

    async def _check_model_health(self, model: ModelConfig) -> bool:
        """Check if a model is available in Ollama."""
        try:
            # Try to get model info
            response = await self._client.post(
                f"{self.ollama_base_url}/api/show",
                json={"name": model.ollama_name},
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning("Health check failed for %s: %s", model.name, e)
            return False

    def get_best_model(self, task_type: TaskType) -> ModelState | None:
        """Get the best available model for a task type.

        Args:
            task_type: Type of task to perform

        Returns:
            Best ModelState or None if no models available
        """
        candidates = []

        for state in self._states.values():
            # Must be healthy and have capacity
            if not state.healthy or state.available_capacity == 0:
                continue

            # Prefer models specialized for this task type
            is_specialized = task_type in state.config.task_types
            score = state.score * (2.0 if is_specialized else 1.0)

            candidates.append((score, state))

        if not candidates:
            return None

        # Sort by score (highest first) and return best
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    async def complete(
        self,
        messages: list[dict[str, str]],
        task_type: TaskType = TaskType.GENERAL,
        preferred_model: str | None = None,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        agent: str | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], str]:
        """Route and execute a completion request with retry logic.

        Args:
            messages: Chat messages
            task_type: Type of task for routing
            preferred_model: Force a specific model (optional)
            max_retries: Max retry attempts (default 3)
            retry_backoff: Backoff multiplier between retries (default 1.0s)
            agent: Agent making the request (for metrics tracking)
            **kwargs: Additional parameters for Ollama

        Returns:
            Tuple of (response dict, model_name used)
        """
        # Select model
        if preferred_model and preferred_model in self._states:
            state = self._states[preferred_model]
            if not state.healthy:
                logger.warning("Preferred model %s unhealthy, routing elsewhere", preferred_model)
                state = self.get_best_model(task_type)
        else:
            state = self.get_best_model(task_type)

        if state is None:
            raise RuntimeError(f"No available models for task type: {task_type}")

        model_name = state.config.name
        state.current_load += 1

        # Generate unique request ID for metrics correlation
        request_id = str(uuid.uuid4())

        # Emit event
        if self.event_bus:
            from agentfarm.events import Event, EventType as ET
            await self.event_bus.emit(Event(
                type=ET.LLM_REQUEST,
                source="router",
                data={
                    "request_id": request_id,
                    "model": model_name,
                    "task_type": task_type.value,
                    "agent": agent,
                    "messages_count": len(messages),
                },
            ))

        start_time = time.time()
        success = False
        last_error: Exception | None = None
        tried_models: set[str] = set()

        for attempt in range(max_retries):
            try:
                response = await self._call_ollama(
                    model=state.config.ollama_name,
                    messages=messages,
                    timeout=state.config.timeout,
                    **kwargs,
                )
                success = True

                # Record success metrics
                state.current_load -= 1
                latency_ms = (time.time() - start_time) * 1000
                state.record_request(latency_ms, success=True)

                # Extract token counts from Ollama response
                input_tokens = response.get("prompt_eval_count", 0)
                output_tokens = response.get("eval_count", 0)

                if self.event_bus:
                    from agentfarm.events import Event, EventType as ET
                    await self.event_bus.emit(Event(
                        type=ET.LLM_RESPONSE,
                        source="router",
                        data={
                            "request_id": request_id,
                            "model": model_name,
                            "agent": agent,
                            "success": True,
                            "latency_ms": latency_ms,
                            "attempts": attempt + 1,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                        },
                    ))

                return response, model_name

            except Exception as e:
                last_error = e
                tried_models.add(model_name)
                logger.warning(
                    "Model %s failed (attempt %d/%d): %s",
                    model_name, attempt + 1, max_retries, e
                )

                # Mark model as unhealthy
                state.healthy = False

                # Try to find a fallback model we haven't tried
                fallback = self.get_best_model(task_type)
                while fallback and fallback.config.name in tried_models:
                    fallback.healthy = False  # Skip this one
                    fallback = self.get_best_model(task_type)

                if fallback:
                    logger.info(
                        "Falling back to %s (attempt %d/%d)",
                        fallback.config.name, attempt + 1, max_retries
                    )
                    state = fallback
                    model_name = state.config.name
                    state.current_load += 1
                else:
                    # No more models, wait and retry current
                    if attempt < max_retries - 1:
                        wait_time = retry_backoff * (2 ** attempt)
                        logger.info("No fallback available, waiting %.1fs before retry", wait_time)
                        await asyncio.sleep(wait_time)
                        # Re-check health
                        for s in self._states.values():
                            if s.config.name not in tried_models:
                                s.healthy = await self._check_model_health(s.config)

        # All retries exhausted - record failure metrics
        state.current_load -= 1
        latency_ms = (time.time() - start_time) * 1000
        state.record_request(latency_ms, success=False)

        if self.event_bus:
            from agentfarm.events import Event, EventType as ET
            await self.event_bus.emit(Event(
                type=ET.LLM_RESPONSE,
                source="router",
                data={
                    "request_id": request_id,
                    "model": model_name,
                    "agent": agent,
                    "success": False,
                    "latency_ms": latency_ms,
                    "retries_exhausted": True,
                    "error": str(last_error) if last_error else None,
                    "input_tokens": 0,
                    "output_tokens": 0,
                },
            ))

        raise RuntimeError(
            f"All {max_retries} retries failed for task {task_type.value}. "
            f"Tried models: {tried_models}. Last error: {last_error}"
        )

    async def _call_ollama(
        self,
        model: str,
        messages: list[dict[str, str]],
        timeout: float = 120.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make a request to Ollama API."""
        response = await self._client.post(
            f"{self.ollama_base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                **kwargs,
            },
            timeout=timeout,
        )

        if response.status_code != 200:
            raise RuntimeError(f"Ollama error: {response.status_code} - {response.text}")

        return response.json()

    async def stream(
        self,
        messages: list[dict[str, str]],
        task_type: TaskType = TaskType.GENERAL,
        agent: str | None = None,
        **kwargs: Any,
    ):
        """Stream a completion request.

        Args:
            messages: Chat messages
            task_type: Type of task for routing
            agent: Agent name (for stream event tracking)

        Yields:
            Chunks from the LLM response
        """
        state = self.get_best_model(task_type)
        if state is None:
            raise RuntimeError(f"No available models for task type: {task_type}")

        state.current_load += 1
        request_id = str(uuid.uuid4())
        model_name = state.config.name

        # Emit stream start
        if self.event_bus:
            from agentfarm.events import Event, EventType as ET
            await self.event_bus.emit(Event(
                type=ET.LLM_REQUEST,
                source="router",
                data={
                    "request_id": request_id,
                    "model": model_name,
                    "agent": agent,
                    "task_type": task_type.value,
                    "streaming": True,
                },
            ))

        start_time = time.time()
        total_tokens = 0

        try:
            async with self._client.stream(
                "POST",
                f"{self.ollama_base_url}/api/chat",
                json={
                    "model": state.config.ollama_name,
                    "messages": messages,
                    "stream": True,
                    **kwargs,
                },
                timeout=state.config.timeout,
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if "message" in data:
                            chunk = data["message"].get("content", "")
                            total_tokens += 1  # Rough estimate
                            yield chunk

                            # Emit stream chunk event with content
                            if self.event_bus and chunk:
                                from agentfarm.events import Event, EventType as ET
                                await self.event_bus.emit(Event(
                                    type=ET.LLM_STREAM_CHUNK,
                                    source="router",
                                    data={
                                        "request_id": request_id,
                                        "model": model_name,
                                        "agent": agent,
                                        "chunk": chunk,
                                    },
                                ))

            # Emit stream completion
            latency_ms = (time.time() - start_time) * 1000
            if self.event_bus:
                from agentfarm.events import Event, EventType as ET
                await self.event_bus.emit(Event(
                    type=ET.LLM_RESPONSE,
                    source="router",
                    data={
                        "request_id": request_id,
                        "model": model_name,
                        "agent": agent,
                        "success": True,
                        "streaming": True,
                        "latency_ms": latency_ms,
                        "output_tokens": total_tokens,
                    },
                ))

        finally:
            state.current_load -= 1

    def get_status(self) -> dict[str, Any]:
        """Get current router status."""
        return {
            "initialized": self._initialized,
            "models": {
                name: {
                    "healthy": state.healthy,
                    "load": state.current_load,
                    "max_load": state.config.max_concurrent,
                    "requests": state.total_requests,
                    "errors": state.total_errors,
                    "avg_latency_ms": round(state.avg_latency_ms, 1),
                    "score": round(state.score, 2),
                    "task_types": [t.value for t in state.config.task_types],
                }
                for name, state in self._states.items()
            },
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


# Agent to task type mapping
AGENT_TASK_TYPES = {
    "planner": TaskType.PLANNING,
    "executor": TaskType.CODE_GENERATION,
    "verifier": TaskType.VERIFICATION,
    "reviewer": TaskType.CODE_REVIEW,
    "ux": TaskType.GENERAL,
    "orchestrator": TaskType.REASONING,
}


def get_task_type_for_agent(agent_name: str) -> TaskType:
    """Get the optimal task type for an agent."""
    return AGENT_TASK_TYPES.get(agent_name.lower(), TaskType.GENERAL)
