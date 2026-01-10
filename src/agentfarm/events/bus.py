"""Async event bus for agent orchestration.

Features:
- Pub/sub with async handlers
- Priority queue for interrupts
- Correlation IDs for tracking related events
- Event history for replay/debugging
- WebSocket broadcast integration
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events in the system."""

    # Workflow lifecycle
    WORKFLOW_START = auto()
    WORKFLOW_COMPLETE = auto()
    WORKFLOW_ERROR = auto()

    # Step execution
    STEP_START = auto()
    STEP_COMPLETE = auto()
    STEP_FAILED = auto()
    STEP_PROGRESS = auto()

    # Agent communication
    AGENT_MESSAGE = auto()
    AGENT_THINKING = auto()
    AGENT_TOOL_CALL = auto()
    AGENT_TOOL_RESULT = auto()

    # Code events (for reviewer to react)
    CODE_GENERATED = auto()
    CODE_MODIFIED = auto()
    FILE_CREATED = auto()
    FILE_DELETED = auto()

    # Collaboration
    COLLABORATION_START = auto()
    COLLABORATION_RESPONSE = auto()
    REVIEW_REQUESTED = auto()
    REVIEW_COMPLETE = auto()

    # Verification
    VERIFICATION_NEEDED = auto()
    VERIFICATION_COMPLETE = auto()
    TEST_STARTED = auto()
    TEST_RESULT = auto()

    # Priority/Interrupt
    INTERRUPT = auto()
    USER_INPUT = auto()
    ERROR_CRITICAL = auto()

    # LLM routing
    LLM_REQUEST = auto()
    LLM_RESPONSE = auto()
    LLM_STREAM_CHUNK = auto()

    # System
    CHECKPOINT = auto()
    HEARTBEAT = auto()


class PriorityLevel(Enum):
    """Priority levels for events."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3  # Interrupts current processing


@dataclass
class Event:
    """An event in the system."""

    type: EventType
    source: str  # Agent or component name
    data: dict[str, Any] = field(default_factory=dict)
    priority: PriorityLevel = PriorityLevel.NORMAL
    correlation_id: str = ""  # Links related events
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def __post_init__(self) -> None:
        if not self.correlation_id:
            self.correlation_id = self.id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "id": self.id,
            "type": self.type.name,
            "source": self.source,
            "data": self.data,
            "priority": self.priority.name,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        """Create from dict."""
        return cls(
            id=d.get("id", ""),
            type=EventType[d["type"]],
            source=d["source"],
            data=d.get("data", {}),
            priority=PriorityLevel[d.get("priority", "NORMAL")],
            correlation_id=d.get("correlation_id", ""),
            timestamp=d.get("timestamp", time.time()),
        )


# Type alias for event handlers
EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """Async pub/sub event bus with priority queue.

    Usage:
        bus = EventBus()

        # Subscribe to events
        async def on_code_generated(event: Event):
            code = event.data["code"]
            # React to code...

        bus.subscribe(EventType.CODE_GENERATED, on_code_generated)

        # Emit events
        await bus.emit(Event(
            type=EventType.CODE_GENERATED,
            source="executor",
            data={"code": "def hello(): pass"}
        ))

        # Start the event loop (for background processing)
        asyncio.create_task(bus.run())
    """

    def __init__(
        self,
        max_history: int = 1000,
        enable_priority_queue: bool = True,
    ):
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._global_subscribers: list[EventHandler] = []  # Receive ALL events
        self._queue: asyncio.PriorityQueue[tuple[int, float, Event]] = asyncio.PriorityQueue()
        self._priority_queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._history: list[Event] = []
        self._max_history = max_history
        self._enable_priority_queue = enable_priority_queue
        self._paused = False

        # Metrics
        self._events_processed = 0
        self._events_by_type: dict[EventType, int] = {}

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> Callable[[], None]:
        """Subscribe to a specific event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Async function to call when event occurs

        Returns:
            Unsubscribe function
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        self._subscribers[event_type].append(handler)
        logger.debug("Subscribed handler to %s", event_type.name)

        def unsubscribe() -> None:
            self._subscribers[event_type].remove(handler)

        return unsubscribe

    def subscribe_all(self, handler: EventHandler) -> Callable[[], None]:
        """Subscribe to ALL events (useful for logging/UI).

        Args:
            handler: Async function to call for every event

        Returns:
            Unsubscribe function
        """
        self._global_subscribers.append(handler)

        def unsubscribe() -> None:
            self._global_subscribers.remove(handler)

        return unsubscribe

    async def emit(self, event: Event) -> None:
        """Emit an event (non-blocking, queued).

        Args:
            event: Event to emit
        """
        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        # Track metrics
        self._events_by_type[event.type] = self._events_by_type.get(event.type, 0) + 1

        # Priority events go to separate queue
        if event.priority == PriorityLevel.CRITICAL:
            await self._priority_queue.put(event)
            logger.info("Critical event queued: %s from %s", event.type.name, event.source)
        else:
            # Priority value (negated so higher priority = lower number = processed first)
            priority_value = -event.priority.value
            await self._queue.put((priority_value, event.timestamp, event))

        logger.debug("Event emitted: %s from %s", event.type.name, event.source)

    async def emit_and_wait(self, event: Event) -> list[Any]:
        """Emit event and wait for all handlers to complete.

        Args:
            event: Event to emit

        Returns:
            List of handler results (or exceptions)
        """
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        handlers = self._get_handlers(event.type)

        if not handlers:
            return []

        results = await asyncio.gather(
            *[h(event) for h in handlers],
            return_exceptions=True,
        )

        self._events_processed += 1
        return results

    def _get_handlers(self, event_type: EventType) -> list[EventHandler]:
        """Get all handlers for an event type."""
        specific = self._subscribers.get(event_type, [])
        return specific + self._global_subscribers

    async def _process_event(self, event: Event) -> None:
        """Process a single event by calling all handlers."""
        handlers = self._get_handlers(event.type)

        if not handlers:
            logger.debug("No handlers for %s", event.type.name)
            return

        # Run handlers concurrently
        results = await asyncio.gather(
            *[h(event) for h in handlers],
            return_exceptions=True,
        )

        # Log any errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Handler error for %s: %s",
                    event.type.name,
                    result,
                    exc_info=result,
                )

        self._events_processed += 1

    async def run(self) -> None:
        """Run the event processing loop.

        Call this to start background event processing.
        Use asyncio.create_task(bus.run()) to run in background.
        """
        self._running = True
        logger.info("EventBus started")

        while self._running:
            # Check priority queue first
            if self._enable_priority_queue:
                try:
                    priority_event = self._priority_queue.get_nowait()
                    logger.info(
                        "Processing critical event: %s",
                        priority_event.type.name,
                    )
                    await self._process_event(priority_event)
                    continue
                except asyncio.QueueEmpty:
                    pass

            # Skip normal events if paused
            if self._paused:
                await asyncio.sleep(0.1)
                continue

            # Process normal queue
            try:
                _, _, event = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=0.1,
                )
                await self._process_event(event)
            except asyncio.TimeoutError:
                # No events, just loop
                pass
            except Exception as e:
                logger.error("Error in event loop: %s", e)

        logger.info("EventBus stopped")

    def stop(self) -> None:
        """Stop the event processing loop."""
        self._running = False

    def pause(self) -> None:
        """Pause normal event processing (priority events still processed)."""
        self._paused = True
        logger.info("EventBus paused")

    def resume(self) -> None:
        """Resume normal event processing."""
        self._paused = False
        logger.info("EventBus resumed")

    async def has_priority_event(self) -> bool:
        """Check if there's a critical event waiting."""
        return not self._priority_queue.empty()

    async def get_priority_event(self) -> Event | None:
        """Get the next priority event (non-blocking)."""
        try:
            return self._priority_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def get_history(
        self,
        event_type: EventType | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get event history with optional filtering.

        Args:
            event_type: Filter by event type
            correlation_id: Filter by correlation ID
            limit: Max events to return

        Returns:
            List of events (newest first)
        """
        events = self._history.copy()

        if event_type:
            events = [e for e in events if e.type == event_type]

        if correlation_id:
            events = [e for e in events if e.correlation_id == correlation_id]

        return events[-limit:][::-1]

    def get_metrics(self) -> dict[str, Any]:
        """Get event bus metrics."""
        return {
            "events_processed": self._events_processed,
            "events_queued": self._queue.qsize(),
            "priority_queued": self._priority_queue.qsize(),
            "history_size": len(self._history),
            "events_by_type": {
                t.name: c for t, c in self._events_by_type.items()
            },
            "running": self._running,
            "paused": self._paused,
        }

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()


# Convenience functions for common events

def workflow_start_event(task: str, provider: str, correlation_id: str = "") -> Event:
    """Create a workflow start event."""
    return Event(
        type=EventType.WORKFLOW_START,
        source="orchestrator",
        data={"task": task, "provider": provider},
        correlation_id=correlation_id or str(uuid.uuid4())[:8],
    )


def agent_message_event(
    agent: str,
    content: str,
    correlation_id: str,
) -> Event:
    """Create an agent message event."""
    return Event(
        type=EventType.AGENT_MESSAGE,
        source=agent,
        data={"content": content},
        correlation_id=correlation_id,
    )


def code_generated_event(
    agent: str,
    code: str,
    file_path: str,
    correlation_id: str,
) -> Event:
    """Create a code generated event."""
    return Event(
        type=EventType.CODE_GENERATED,
        source=agent,
        data={"code": code, "file_path": file_path},
        correlation_id=correlation_id,
    )


def interrupt_event(
    source: str,
    reason: str,
    correlation_id: str,
) -> Event:
    """Create an interrupt event (critical priority)."""
    return Event(
        type=EventType.INTERRUPT,
        source=source,
        data={"reason": reason},
        priority=PriorityLevel.CRITICAL,
        correlation_id=correlation_id,
    )
