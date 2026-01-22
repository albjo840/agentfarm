"""Workflow progress tracking with weighted phases."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Awaitable

if TYPE_CHECKING:
    from agentfarm.events.bus import EventBus

logger = logging.getLogger(__name__)


class WorkflowPhase(Enum):
    """Workflow phases with their relative weights."""

    PLAN = "plan"
    UX_DESIGN = "ux_design"
    EXECUTE = "execute"
    VERIFY = "verify"
    REVIEW = "review"
    SUMMARY = "summary"


# Default phase weights (should sum to 100)
DEFAULT_PHASE_WEIGHTS: dict[WorkflowPhase, float] = {
    WorkflowPhase.PLAN: 10.0,
    WorkflowPhase.UX_DESIGN: 5.0,  # Often skipped
    WorkflowPhase.EXECUTE: 50.0,
    WorkflowPhase.VERIFY: 15.0,
    WorkflowPhase.REVIEW: 15.0,
    WorkflowPhase.SUMMARY: 5.0,
}


@dataclass
class PhaseProgress:
    """Progress within a single phase."""

    phase: WorkflowPhase
    total_steps: int = 1
    completed_steps: int = 0
    started_at: float | None = None
    completed_at: float | None = None
    status: str = "pending"  # pending, active, complete, error, skipped

    @property
    def phase_percent(self) -> float:
        """Progress within this phase (0-100)."""
        if self.total_steps == 0:
            return 100.0 if self.status == "complete" else 0.0
        return (self.completed_steps / self.total_steps) * 100.0

    @property
    def duration_seconds(self) -> float | None:
        """Duration of this phase in seconds."""
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return end - self.started_at

    def start(self) -> None:
        """Mark phase as started."""
        self.started_at = time.time()
        self.status = "active"

    def complete(self, success: bool = True) -> None:
        """Mark phase as complete."""
        self.completed_at = time.time()
        self.status = "complete" if success else "error"
        self.completed_steps = self.total_steps

    def skip(self) -> None:
        """Mark phase as skipped."""
        self.status = "skipped"
        self.completed_at = time.time()

    def increment(self, count: int = 1) -> None:
        """Increment completed steps."""
        self.completed_steps = min(self.completed_steps + count, self.total_steps)


@dataclass
class WorkflowProgress:
    """Overall workflow progress tracking."""

    phases: dict[WorkflowPhase, PhaseProgress] = field(default_factory=dict)
    phase_weights: dict[WorkflowPhase, float] = field(
        default_factory=lambda: DEFAULT_PHASE_WEIGHTS.copy()
    )
    started_at: float | None = None
    completed_at: float | None = None
    current_phase: WorkflowPhase | None = None

    def __post_init__(self) -> None:
        """Initialize phases if not provided."""
        for phase in WorkflowPhase:
            if phase not in self.phases:
                self.phases[phase] = PhaseProgress(phase=phase)

    @property
    def total_percent(self) -> float:
        """Overall workflow progress (0-100)."""
        total_weight = sum(self.phase_weights.values())
        if total_weight == 0:
            return 0.0

        weighted_progress = 0.0
        for phase, progress in self.phases.items():
            weight = self.phase_weights.get(phase, 0.0)
            if progress.status == "skipped":
                # Skipped phases count as complete for progress
                weighted_progress += weight
            elif progress.status in ("complete", "error"):
                weighted_progress += weight
            elif progress.status == "active":
                # Partial progress
                weighted_progress += weight * (progress.phase_percent / 100.0)

        return (weighted_progress / total_weight) * 100.0

    @property
    def duration_seconds(self) -> float | None:
        """Total workflow duration."""
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return end - self.started_at

    def start_workflow(self) -> None:
        """Mark workflow as started."""
        self.started_at = time.time()

    def complete_workflow(self) -> None:
        """Mark workflow as complete."""
        self.completed_at = time.time()

    def start_phase(self, phase: WorkflowPhase, total_steps: int = 1) -> None:
        """Start a workflow phase."""
        self.current_phase = phase
        self.phases[phase].total_steps = total_steps
        self.phases[phase].start()
        logger.debug(
            "Started phase %s with %d steps (progress: %.1f%%)",
            phase.value,
            total_steps,
            self.total_percent,
        )

    def complete_phase(self, phase: WorkflowPhase, success: bool = True) -> None:
        """Complete a workflow phase."""
        self.phases[phase].complete(success)
        logger.debug(
            "Completed phase %s (success=%s, progress: %.1f%%)",
            phase.value,
            success,
            self.total_percent,
        )

    def skip_phase(self, phase: WorkflowPhase) -> None:
        """Skip a workflow phase."""
        self.phases[phase].skip()
        logger.debug(
            "Skipped phase %s (progress: %.1f%%)",
            phase.value,
            self.total_percent,
        )

    def update_step(self, phase: WorkflowPhase, completed_steps: int) -> None:
        """Update step progress within a phase."""
        self.phases[phase].completed_steps = completed_steps
        logger.debug(
            "Phase %s: %d/%d steps (progress: %.1f%%)",
            phase.value,
            completed_steps,
            self.phases[phase].total_steps,
            self.total_percent,
        )

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of workflow progress."""
        return {
            "total_percent": round(self.total_percent, 1),
            "current_phase": self.current_phase.value if self.current_phase else None,
            "duration_seconds": self.duration_seconds,
            "phases": {
                phase.value: {
                    "status": progress.status,
                    "percent": round(progress.phase_percent, 1),
                    "steps": f"{progress.completed_steps}/{progress.total_steps}",
                    "duration": progress.duration_seconds,
                }
                for phase, progress in self.phases.items()
            },
        }


class ProgressTracker:
    """Tracks and emits workflow progress events.

    Example usage:
        tracker = ProgressTracker(event_bus=bus)

        # Start workflow
        tracker.start_workflow("Add feature X")

        # Track phases
        tracker.start_phase(WorkflowPhase.PLAN, total_steps=1)
        tracker.complete_phase(WorkflowPhase.PLAN)

        tracker.start_phase(WorkflowPhase.EXECUTE, total_steps=5)
        for i in range(5):
            tracker.update_step(WorkflowPhase.EXECUTE, i + 1)
        tracker.complete_phase(WorkflowPhase.EXECUTE)

        # Finish
        tracker.complete_workflow()
        print(f"Total progress: {tracker.progress.total_percent}%")
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        event_callback: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        phase_weights: dict[WorkflowPhase, float] | None = None,
    ) -> None:
        """Initialize progress tracker.

        Args:
            event_bus: Optional EventBus for emitting events
            event_callback: Optional async callback for progress events
            phase_weights: Custom phase weights (default: 10/5/50/15/15/5)
        """
        self.event_bus = event_bus
        self.event_callback = event_callback
        self.progress = WorkflowProgress(
            phase_weights=phase_weights or DEFAULT_PHASE_WEIGHTS.copy()
        )
        self._task_description: str = ""

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit a progress event."""
        # Add common fields
        data["total_percent"] = round(self.progress.total_percent, 1)
        data["task"] = self._task_description

        if self.event_callback:
            await self.event_callback(event_type, data)

        if self.event_bus:
            from agentfarm.events.bus import Event, EventType as ET, PriorityLevel

            # Map to EventType if applicable
            event_mapping = {
                "workflow_progress": ET.WORKFLOW_START,
                "phase_start": ET.STEP_START,
                "phase_complete": ET.STEP_COMPLETE,
            }
            et = event_mapping.get(event_type, ET.WORKFLOW_START)

            await self.event_bus.emit(
                Event(
                    type=et,
                    source="progress_tracker",
                    data=data,
                    priority=PriorityLevel.NORMAL,
                )
            )

    async def start_workflow(self, task_description: str) -> None:
        """Start tracking a workflow."""
        self._task_description = task_description
        self.progress.start_workflow()
        await self._emit("workflow_progress", {
            "status": "started",
            "phase": None,
        })

    async def complete_workflow(self, success: bool = True) -> None:
        """Complete the workflow."""
        self.progress.complete_workflow()
        await self._emit("workflow_progress", {
            "status": "complete" if success else "error",
            "duration_seconds": self.progress.duration_seconds,
        })

    async def start_phase(
        self,
        phase: WorkflowPhase,
        total_steps: int = 1,
    ) -> None:
        """Start a workflow phase."""
        self.progress.start_phase(phase, total_steps)
        await self._emit("phase_start", {
            "phase": phase.value,
            "total_steps": total_steps,
        })

    async def complete_phase(
        self,
        phase: WorkflowPhase,
        success: bool = True,
    ) -> None:
        """Complete a workflow phase."""
        self.progress.complete_phase(phase, success)
        await self._emit("phase_complete", {
            "phase": phase.value,
            "success": success,
            "duration_seconds": self.progress.phases[phase].duration_seconds,
        })

    async def skip_phase(self, phase: WorkflowPhase) -> None:
        """Skip a workflow phase."""
        self.progress.skip_phase(phase)
        await self._emit("phase_skip", {
            "phase": phase.value,
        })

    async def update_step(
        self,
        phase: WorkflowPhase,
        completed_steps: int,
        step_description: str = "",
    ) -> None:
        """Update step progress within a phase."""
        self.progress.update_step(phase, completed_steps)
        await self._emit("step_progress", {
            "phase": phase.value,
            "completed_steps": completed_steps,
            "total_steps": self.progress.phases[phase].total_steps,
            "step_description": step_description,
        })

    def get_summary(self) -> dict[str, Any]:
        """Get progress summary."""
        return self.progress.get_summary()
