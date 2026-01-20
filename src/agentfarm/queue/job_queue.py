"""Priority-based job queue for GPU workflows.

Handles concurrent workflow execution with:
- Priority queue (Beta Operator > Free users)
- Configurable max concurrent jobs
- Real-time position updates via callbacks
- Automatic cleanup of completed jobs
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Status of a queued job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(int, Enum):
    """Priority levels for job scheduling."""

    LOW = 0        # Rate-limited users
    NORMAL = 1     # Free tier
    HIGH = 2       # Beta Operator / Paid
    CRITICAL = 3   # Admin / System


@dataclass
class Job:
    """A queued workflow job."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    device_id: str = ""
    task: str = ""
    priority: JobPriority = JobPriority.NORMAL
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Any = None
    error: str | None = None
    position: int = 0  # Position in queue (1-indexed for UI)

    # Internal: workflow function and kwargs (not serialized)
    _workflow_fn: Callable[..., Coroutine] | None = field(default=None, repr=False)
    _workflow_kwargs: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "id": self.id,
            "device_id": self.device_id[:8] if self.device_id else "",
            "task": self.task[:50] + "..." if len(self.task) > 50 else self.task,
            "priority": self.priority.name,
            "status": self.status.value,
            "position": self.position,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class JobQueue:
    """Priority-based job queue for GPU workflows.

    Manages concurrent execution of workflow jobs with:
    - Priority scheduling (higher priority jobs run first)
    - Configurable concurrency limit
    - Real-time status callbacks
    - Automatic cleanup of old completed jobs

    Usage:
        queue = JobQueue(max_concurrent=4)
        await queue.start()

        job = await queue.submit(
            device_id="abc123",
            task="Build a calculator app",
            priority=JobPriority.HIGH,
            workflow_fn=run_workflow,
            task="...",
            working_dir="...",
        )

        # Check status
        status = await queue.get_status(job.id)
    """

    def __init__(
        self,
        max_concurrent: int = 4,
        on_status_change: Callable[[Job], Coroutine] | None = None,
        max_completed_jobs: int = 100,
    ) -> None:
        """Initialize job queue.

        Args:
            max_concurrent: Maximum jobs running at once
            on_status_change: Async callback when job status changes
            max_completed_jobs: How many completed jobs to keep in history
        """
        self.max_concurrent = max_concurrent
        self.on_status_change = on_status_change
        self.max_completed_jobs = max_completed_jobs

        self._queue: list[Job] = []
        self._running: dict[str, Job] = {}
        self._completed: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._worker_task: asyncio.Task | None = None
        self._started = False

    @property
    def is_running(self) -> bool:
        """Check if queue worker is running."""
        return self._started and self._worker_task is not None

    async def start(self) -> None:
        """Start the queue worker."""
        if self._started:
            return

        self._started = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("JobQueue started (max_concurrent=%d)", self.max_concurrent)

    async def stop(self) -> None:
        """Stop the queue worker gracefully."""
        if not self._started:
            return

        self._started = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

        logger.info("JobQueue stopped")

    async def submit(
        self,
        device_id: str,
        task: str,
        priority: JobPriority = JobPriority.NORMAL,
        workflow_fn: Callable[..., Coroutine] | None = None,
        **workflow_kwargs: Any,
    ) -> Job:
        """Submit a job to the queue.

        Args:
            device_id: User identifier
            task: Task description (for display)
            priority: Job priority level
            workflow_fn: Async function to execute
            **workflow_kwargs: Arguments to pass to workflow_fn

        Returns:
            Job object with queue position
        """
        job = Job(
            device_id=device_id,
            task=task[:200],  # Truncate for display
            priority=priority,
        )
        job._workflow_fn = workflow_fn
        job._workflow_kwargs = workflow_kwargs

        async with self._lock:
            # Insert by priority (higher priority = earlier in queue)
            insert_pos = len(self._queue)
            for i, queued_job in enumerate(self._queue):
                if job.priority > queued_job.priority:
                    insert_pos = i
                    break

            self._queue.insert(insert_pos, job)
            await self._update_positions()

        await self._notify(job)
        logger.info(
            "Job %s queued (user=%s, priority=%s, position=%d)",
            job.id,
            device_id[:8] if device_id else "anon",
            job.priority.name,
            job.position,
        )

        return job

    async def cancel(self, job_id: str, device_id: str | None = None) -> bool:
        """Cancel a queued job.

        Args:
            job_id: Job to cancel
            device_id: If provided, verify ownership

        Returns:
            True if cancelled, False if not found or unauthorized
        """
        async with self._lock:
            for i, job in enumerate(self._queue):
                if job.id == job_id:
                    # Check ownership if device_id provided
                    if device_id and job.device_id != device_id:
                        return False

                    job.status = JobStatus.CANCELLED
                    self._queue.pop(i)
                    self._completed[job.id] = job
                    await self._update_positions()
                    await self._notify(job)
                    logger.info("Job %s cancelled", job_id)
                    return True

        return False

    async def get_status(self, job_id: str) -> Job | None:
        """Get job by ID."""
        async with self._lock:
            # Check running
            if job_id in self._running:
                return self._running[job_id]

            # Check queue
            for job in self._queue:
                if job.id == job_id:
                    return job

            # Check completed
            return self._completed.get(job_id)

    async def get_queue_info(self) -> dict[str, Any]:
        """Get queue statistics."""
        async with self._lock:
            return {
                "queued": len(self._queue),
                "running": len(self._running),
                "completed": len(self._completed),
                "max_concurrent": self.max_concurrent,
                "available_slots": max(0, self.max_concurrent - len(self._running)),
                "estimated_wait_minutes": len(self._queue) * 2,  # ~2 min per job
            }

    async def get_user_jobs(self, device_id: str) -> list[Job]:
        """Get all jobs for a user."""
        jobs = []
        async with self._lock:
            for job in self._queue:
                if job.device_id == device_id:
                    jobs.append(job)
            for job in self._running.values():
                if job.device_id == device_id:
                    jobs.append(job)
        return jobs

    async def get_user_position(self, device_id: str) -> int | None:
        """Get user's position in queue (1-indexed, None if not queued)."""
        async with self._lock:
            for job in self._queue:
                if job.device_id == device_id:
                    return job.position
            return None

    async def get_queue_snapshot(self) -> list[dict[str, Any]]:
        """Get snapshot of queue for admin view."""
        async with self._lock:
            snapshot = []
            # Running jobs first
            for job in self._running.values():
                snapshot.append(job.to_dict())
            # Then queued
            for job in self._queue:
                snapshot.append(job.to_dict())
            return snapshot

    async def _worker(self) -> None:
        """Background worker that processes the queue."""
        while self._started:
            try:
                await self._process_next()
                await asyncio.sleep(0.1)  # Small delay between checks
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Queue worker error: %s", e)
                await asyncio.sleep(1)

    async def _process_next(self) -> None:
        """Process next job if capacity available."""
        async with self._lock:
            # Check if we have capacity
            if len(self._running) >= self.max_concurrent:
                return

            # Check if there are jobs waiting
            if not self._queue:
                return

            # Take next job
            job = self._queue.pop(0)
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now()
            job.position = 0  # No longer in queue
            self._running[job.id] = job
            await self._update_positions()

        await self._notify(job)
        logger.info("Job %s started", job.id)

        # Run workflow in background task
        asyncio.create_task(self._run_job(job))

    async def _run_job(self, job: Job) -> None:
        """Execute the job's workflow."""
        try:
            if job._workflow_fn:
                job.result = await job._workflow_fn(**job._workflow_kwargs)
            job.status = JobStatus.COMPLETED
            logger.info("Job %s completed", job.id)
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            logger.error("Job %s failed: %s", job.id, e)
        finally:
            job.completed_at = datetime.now()

            async with self._lock:
                # Move from running to completed
                if job.id in self._running:
                    del self._running[job.id]
                self._completed[job.id] = job

                # Cleanup old completed jobs
                await self._cleanup_completed()

            await self._notify(job)

    async def _update_positions(self) -> None:
        """Update position numbers for queued jobs (1-indexed)."""
        for i, job in enumerate(self._queue):
            old_pos = job.position
            job.position = i + 1
            # Notify if position changed
            if old_pos != job.position and old_pos > 0:
                await self._notify(job)

    async def _cleanup_completed(self) -> None:
        """Remove oldest completed jobs if over limit."""
        while len(self._completed) > self.max_completed_jobs:
            # Find oldest
            oldest_id = None
            oldest_time = datetime.now()
            for job_id, job in self._completed.items():
                if job.completed_at and job.completed_at < oldest_time:
                    oldest_time = job.completed_at
                    oldest_id = job_id

            if oldest_id:
                del self._completed[oldest_id]

    async def _notify(self, job: Job) -> None:
        """Notify about job status change via callback."""
        if self.on_status_change:
            try:
                await self.on_status_change(job)
            except Exception as e:
                logger.warning("Status notification failed for job %s: %s", job.id, e)


# Global queue instance
_job_queue: JobQueue | None = None


def get_job_queue() -> JobQueue | None:
    """Get the global job queue (may be None if not initialized)."""
    return _job_queue


async def init_job_queue(
    max_concurrent: int = 4,
    on_status_change: Callable[[Job], Coroutine] | None = None,
) -> JobQueue:
    """Initialize and start the global job queue.

    Args:
        max_concurrent: Max concurrent jobs (default 4 for Ollama)
        on_status_change: Callback for job status updates

    Returns:
        The initialized JobQueue
    """
    global _job_queue

    if _job_queue is not None:
        await _job_queue.stop()

    _job_queue = JobQueue(
        max_concurrent=max_concurrent,
        on_status_change=on_status_change,
    )
    await _job_queue.start()

    return _job_queue


async def shutdown_job_queue() -> None:
    """Shutdown the global job queue."""
    global _job_queue
    if _job_queue:
        await _job_queue.stop()
        _job_queue = None
