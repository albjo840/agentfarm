"""Workflow state persistence for resume after disconnect.

Saves workflow state to disk so it can be resumed if the connection breaks.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import time

from agentfarm.events.bus import Event, EventBus, EventType

logger = logging.getLogger(__name__)


@dataclass
class WorkflowState:
    """Persistent state for a workflow."""

    correlation_id: str
    task: str
    status: str = "running"  # running, paused, completed, failed
    current_step: int = 0
    total_steps: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    events: list[dict[str, Any]] = field(default_factory=list)
    checkpoint_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowState:
        return cls(**data)

    def add_event(self, event: Event) -> None:
        """Add an event to the state."""
        self.events.append(event.to_dict())
        self.updated_at = time.time()

    def set_checkpoint(self, key: str, value: Any) -> None:
        """Save checkpoint data."""
        self.checkpoint_data[key] = value
        self.updated_at = time.time()


class WorkflowPersistence:
    """Persists workflow state to disk for resume capability.

    Usage:
        persistence = WorkflowPersistence(storage_dir=".agentfarm/workflows")

        # Connect to event bus
        persistence.connect(event_bus)

        # Get active workflows
        workflows = persistence.list_workflows()

        # Resume a workflow
        state = persistence.load_workflow("abc123")
    """

    def __init__(
        self,
        storage_dir: str | Path = ".agentfarm/workflows",
        auto_save_interval: float = 5.0,  # Save every 5 seconds
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.auto_save_interval = auto_save_interval

        self._workflows: dict[str, WorkflowState] = {}
        self._event_bus: EventBus | None = None
        self._save_task: asyncio.Task | None = None
        self._running = False

    def connect(self, event_bus: EventBus) -> None:
        """Connect to event bus and start listening for events."""
        self._event_bus = event_bus

        # Subscribe to relevant events
        event_bus.subscribe(EventType.WORKFLOW_START, self._on_workflow_start)
        event_bus.subscribe(EventType.WORKFLOW_COMPLETE, self._on_workflow_complete)
        event_bus.subscribe(EventType.WORKFLOW_ERROR, self._on_workflow_error)
        event_bus.subscribe(EventType.STEP_START, self._on_step_start)
        event_bus.subscribe(EventType.STEP_COMPLETE, self._on_step_complete)
        event_bus.subscribe(EventType.CHECKPOINT, self._on_checkpoint)

        # Also subscribe to all events for full history
        event_bus.subscribe_all(self._on_any_event)

        # Start auto-save task
        self._running = True
        self._save_task = asyncio.create_task(self._auto_save_loop())

        logger.info("WorkflowPersistence connected to EventBus")

    async def _auto_save_loop(self) -> None:
        """Periodically save active workflows to disk."""
        while self._running:
            await asyncio.sleep(self.auto_save_interval)
            for workflow_id, state in self._workflows.items():
                if state.status == "running":
                    self._save_to_disk(workflow_id, state)

    def stop(self) -> None:
        """Stop the persistence system."""
        self._running = False
        if self._save_task:
            self._save_task.cancel()

        # Final save of all active workflows
        for workflow_id, state in self._workflows.items():
            self._save_to_disk(workflow_id, state)

    async def _on_workflow_start(self, event: Event) -> None:
        """Handle workflow start event."""
        workflow_id = event.correlation_id
        task = event.data.get("task", "Unknown task")

        state = WorkflowState(
            correlation_id=workflow_id,
            task=task,
            status="running",
        )

        self._workflows[workflow_id] = state
        self._save_to_disk(workflow_id, state)
        logger.info("Started tracking workflow %s: %s", workflow_id, task[:50])

    async def _on_workflow_complete(self, event: Event) -> None:
        """Handle workflow completion."""
        workflow_id = event.correlation_id
        if workflow_id in self._workflows:
            state = self._workflows[workflow_id]
            state.status = "completed"
            state.updated_at = time.time()
            self._save_to_disk(workflow_id, state)
            logger.info("Workflow %s completed", workflow_id)

    async def _on_workflow_error(self, event: Event) -> None:
        """Handle workflow error."""
        workflow_id = event.correlation_id
        if workflow_id in self._workflows:
            state = self._workflows[workflow_id]
            state.status = "failed"
            state.error = event.data.get("error", "Unknown error")
            state.updated_at = time.time()
            self._save_to_disk(workflow_id, state)
            logger.error("Workflow %s failed: %s", workflow_id, state.error)

    async def _on_step_start(self, event: Event) -> None:
        """Handle step start."""
        workflow_id = event.correlation_id
        if workflow_id in self._workflows:
            state = self._workflows[workflow_id]
            step_id = event.data.get("step_id", 0)
            state.current_step = step_id
            state.updated_at = time.time()

    async def _on_step_complete(self, event: Event) -> None:
        """Handle step completion."""
        workflow_id = event.correlation_id
        if workflow_id in self._workflows:
            state = self._workflows[workflow_id]
            state.updated_at = time.time()
            # Save checkpoint after each step
            self._save_to_disk(workflow_id, state)

    async def _on_checkpoint(self, event: Event) -> None:
        """Handle explicit checkpoint event."""
        workflow_id = event.correlation_id
        if workflow_id in self._workflows:
            state = self._workflows[workflow_id]
            # Merge checkpoint data
            for key, value in event.data.items():
                state.set_checkpoint(key, value)
            self._save_to_disk(workflow_id, state)
            logger.debug("Checkpoint saved for workflow %s", workflow_id)

    async def _on_any_event(self, event: Event) -> None:
        """Track all events for full history."""
        workflow_id = event.correlation_id
        if workflow_id in self._workflows:
            self._workflows[workflow_id].add_event(event)

    def _save_to_disk(self, workflow_id: str, state: WorkflowState) -> None:
        """Save workflow state to disk."""
        file_path = self.storage_dir / f"{workflow_id}.json"
        try:
            with open(file_path, "w") as f:
                json.dump(state.to_dict(), f, indent=2)
        except Exception as e:
            logger.error("Failed to save workflow %s: %s", workflow_id, e)

    def load_workflow(self, workflow_id: str) -> WorkflowState | None:
        """Load a workflow state from disk."""
        file_path = self.storage_dir / f"{workflow_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path) as f:
                data = json.load(f)
            state = WorkflowState.from_dict(data)
            self._workflows[workflow_id] = state
            return state
        except Exception as e:
            logger.error("Failed to load workflow %s: %s", workflow_id, e)
            return None

    def list_workflows(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List workflows with optional status filter.

        Args:
            status: Filter by status (running, paused, completed, failed)
            limit: Max workflows to return

        Returns:
            List of workflow summaries
        """
        workflows = []

        # Check disk for saved workflows
        for file_path in sorted(
            self.storage_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]:
            try:
                with open(file_path) as f:
                    data = json.load(f)

                if status and data.get("status") != status:
                    continue

                workflows.append({
                    "id": data["correlation_id"],
                    "task": data["task"][:100],
                    "status": data["status"],
                    "current_step": data.get("current_step", 0),
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"],
                })
            except Exception:
                continue

        return workflows

    def get_resumable_workflows(self) -> list[dict[str, Any]]:
        """Get workflows that can be resumed (running or paused)."""
        return self.list_workflows(status="running") + self.list_workflows(status="paused")

    def pause_workflow(self, workflow_id: str) -> bool:
        """Pause a running workflow."""
        if workflow_id in self._workflows:
            state = self._workflows[workflow_id]
            if state.status == "running":
                state.status = "paused"
                state.updated_at = time.time()
                self._save_to_disk(workflow_id, state)
                return True
        return False

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow state."""
        file_path = self.storage_dir / f"{workflow_id}.json"
        if file_path.exists():
            file_path.unlink()
            self._workflows.pop(workflow_id, None)
            return True
        return False
