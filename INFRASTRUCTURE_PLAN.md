# AgentFarm Infrastructure Plan

## Nuläge

| Komponent | Status | Fil |
|-----------|--------|-----|
| Docker Sandbox | ✅ Finns | `tools/sandbox.py` |
| TierManager | ✅ Finns | `monetization/tiers.py` |
| Ollama Provider | ✅ Finns | `providers/ollama.py` |
| Job Queue | ❌ Saknas | - |
| Session Isolation | ⚠️ Delvis | Alla delar samma sandbox |

---

## 1. Ollama Concurrency Configuration

### Problem
Ollama hanterar bara en förfrågan i taget som standard. Med flera användare blir det flaskhals.

### Lösning

**Steg 1: Ollama VM-konfiguration**
```bash
# I din Ollama VM (via Proxmox)
# Lägg till i /etc/systemd/system/ollama.service eller .bashrc

export OLLAMA_NUM_PARALLEL=4          # Max 4 parallella requests
export OLLAMA_MAX_LOADED_MODELS=2     # Max 2 modeller i VRAM samtidigt
export OLLAMA_KEEP_ALIVE=5m           # Behåll modell 5 min efter användning
```

**Steg 2: Skapa setup-script**
```bash
# scripts/ollama_setup.sh
#!/bin/bash
# Kör på Ollama VM

cat >> /etc/environment << EOF
OLLAMA_NUM_PARALLEL=4
OLLAMA_MAX_LOADED_MODELS=2
OLLAMA_KEEP_ALIVE=5m
EOF

systemctl restart ollama
```

**VRAM-beräkning för RX 7800 XT (16GB):**
| Modell | VRAM | Max parallella |
|--------|------|----------------|
| llama3.2:3b | ~2GB | 6-8 |
| qwen2.5-coder:7b | ~5GB | 2-3 |
| qwen3:14b | ~9GB | 1 |

### Implementation i AgentFarm

```python
# src/agentfarm/config.py - Lägg till

OLLAMA_CONFIG = {
    "num_parallel": int(os.getenv("OLLAMA_NUM_PARALLEL", 4)),
    "max_loaded_models": int(os.getenv("OLLAMA_MAX_LOADED_MODELS", 2)),
    "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "5m"),
}
```

---

## 2. Job Queue System

### Arkitektur

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Kund A    │    │   Kund B    │    │   Kund C    │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────┐
│                    JobQueue                          │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                   │
│  │Job 1│→│Job 2│→│Job 3│→│Job 4│  (max_concurrent=4)│
│  └─────┘ └─────┘ └─────┘ └─────┘                   │
│                                                      │
│  Priority: Beta Operator > Free                      │
└─────────────────────────────────────────────────────┘
                      │
                      ▼
              ┌───────────────┐
              │  Ollama GPU   │
              │  (4 workers)  │
              └───────────────┘
```

### Implementation

**Ny fil: `src/agentfarm/queue/job_queue.py`**

```python
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(int, Enum):
    LOW = 0       # Free tier
    NORMAL = 1    # Standard
    HIGH = 2      # Beta Operator
    CRITICAL = 3  # Admin


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
    position: int = 0  # Position in queue (for UI)


class JobQueue:
    """Priority-based job queue for GPU workflows.

    Features:
    - Priority queue (Beta Operator > Free)
    - Configurable max concurrent jobs
    - Real-time position updates via callback
    - Automatic cleanup of completed jobs
    """

    def __init__(
        self,
        max_concurrent: int = 4,
        on_status_change: Callable[[Job], Coroutine] | None = None,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.on_status_change = on_status_change

        self._queue: list[Job] = []
        self._running: dict[str, Job] = {}
        self._completed: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the queue worker."""
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())
            logger.info("JobQueue started (max_concurrent=%d)", self.max_concurrent)

    async def stop(self) -> None:
        """Stop the queue worker."""
        if self._worker_task:
            self._worker_task.cancel()
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
        """Submit a job to the queue."""
        job = Job(
            device_id=device_id,
            task=task[:100],  # Truncate for display
            priority=priority,
        )
        job._workflow_fn = workflow_fn
        job._workflow_kwargs = workflow_kwargs

        async with self._lock:
            # Insert by priority (higher priority first)
            insert_pos = 0
            for i, queued_job in enumerate(self._queue):
                if job.priority > queued_job.priority:
                    insert_pos = i
                    break
                insert_pos = i + 1

            self._queue.insert(insert_pos, job)
            await self._update_positions()

        await self._notify(job)
        logger.info("Job %s queued (priority=%s, position=%d)",
                   job.id, job.priority.name, job.position)

        return job

    async def get_status(self, job_id: str) -> Job | None:
        """Get job status."""
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
                "max_concurrent": self.max_concurrent,
                "estimated_wait_minutes": len(self._queue) * 2,  # ~2 min per job
            }

    async def get_user_position(self, device_id: str) -> int | None:
        """Get user's position in queue (1-indexed, None if not queued)."""
        async with self._lock:
            for i, job in enumerate(self._queue):
                if job.device_id == device_id:
                    return i + 1
            return None

    async def _worker(self) -> None:
        """Background worker that processes the queue."""
        while True:
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
            if len(self._running) >= self.max_concurrent:
                return
            if not self._queue:
                return

            job = self._queue.pop(0)
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now()
            self._running[job.id] = job
            await self._update_positions()

        await self._notify(job)

        # Run workflow in background
        asyncio.create_task(self._run_job(job))

    async def _run_job(self, job: Job) -> None:
        """Execute the job's workflow."""
        try:
            if job._workflow_fn:
                job.result = await job._workflow_fn(**job._workflow_kwargs)
            job.status = JobStatus.COMPLETED
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            logger.error("Job %s failed: %s", job.id, e)
        finally:
            job.completed_at = datetime.now()

            async with self._lock:
                del self._running[job.id]
                self._completed[job.id] = job

                # Cleanup old completed jobs (keep last 100)
                if len(self._completed) > 100:
                    oldest = min(self._completed.values(),
                               key=lambda j: j.completed_at or datetime.min)
                    del self._completed[oldest.id]

            await self._notify(job)

    async def _update_positions(self) -> None:
        """Update position numbers for queued jobs."""
        for i, job in enumerate(self._queue):
            job.position = i + 1

    async def _notify(self, job: Job) -> None:
        """Notify about job status change."""
        if self.on_status_change:
            try:
                await self.on_status_change(job)
            except Exception as e:
                logger.warning("Status notification failed: %s", e)


# Global queue instance
_job_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Get the global job queue."""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue(max_concurrent=4)
    return _job_queue


async def init_job_queue(max_concurrent: int = 4) -> JobQueue:
    """Initialize and start the global job queue."""
    global _job_queue
    _job_queue = JobQueue(max_concurrent=max_concurrent)
    await _job_queue.start()
    return _job_queue
```

### Integration i web/server.py

```python
# I websocket_handler, ersätt direkta workflow-anrop:

from agentfarm.queue.job_queue import get_job_queue, JobPriority

async def handle_workflow_request(device_id: str, task: str, is_beta: bool):
    queue = get_job_queue()

    # Check queue status
    info = await queue.get_queue_info()
    if info["queued"] > 20:
        await ws_clients.broadcast({
            "type": "queue_full",
            "message": "Servern är överbelastad. Försök igen senare.",
        })
        return

    # Submit with priority
    priority = JobPriority.HIGH if is_beta else JobPriority.NORMAL
    job = await queue.submit(
        device_id=device_id,
        task=task,
        priority=priority,
        workflow_fn=run_real_workflow,
        task=task,
        provider_type="auto",
        working_dir=current_working_dir,
        device_id=device_id,
    )

    # Notify user of queue position
    if job.position > 1:
        await ws_clients.broadcast({
            "type": "queue_position",
            "job_id": job.id,
            "position": job.position,
            "estimated_wait": info["estimated_wait_minutes"],
            "message": f"Du är nummer {job.position} i kön...",
        })
```

---

## 3. Session-baserad Sandbox Isolation

### Nuläge
Alla användare delar samma sandbox-volym (`working_dir`).

### Förbättring

**Uppdatera `tools/sandbox.py`:**

```python
class SessionSandbox(SandboxRunner):
    """Per-session isolated sandbox with unique volumes."""

    def __init__(
        self,
        session_id: str,
        base_dir: Path,
        **kwargs: Any,
    ) -> None:
        # Create unique session directory
        self.session_id = session_id
        self.session_dir = base_dir / ".sessions" / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        super().__init__(working_dir=str(self.session_dir), **kwargs)

        # Track for cleanup
        self._created_at = datetime.now()
        self._max_age_hours = 4

    def _run_sync(self, command: str, timeout: int, env: dict[str, str]) -> SandboxResult:
        """Run with session-isolated volume."""
        client = self._get_client()
        container_name = f"agentfarm-{self.session_id[:8]}-{uuid.uuid4().hex[:4]}"

        try:
            container = client.containers.create(
                image=self.image,
                command=["sh", "-c", command],
                name=container_name,
                working_dir="/workspace",
                volumes={
                    str(self.session_dir): {
                        "bind": "/workspace",
                        "mode": "rw",  # Session gets read-write
                    }
                },
                # ... rest of security constraints
            )
            # ... run and return result
        finally:
            # Container cleanup (session dir persists until explicit cleanup)
            pass

    async def cleanup(self) -> None:
        """Delete session directory and all files."""
        import shutil
        if self.session_dir.exists():
            shutil.rmtree(self.session_dir)
            logger.info("Session %s cleaned up", self.session_id)


class SandboxManager:
    """Manages session sandboxes with automatic cleanup."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self._sessions: dict[str, SessionSandbox] = {}
        self._cleanup_task: asyncio.Task | None = None

    async def get_sandbox(self, device_id: str) -> SessionSandbox:
        """Get or create sandbox for device."""
        if device_id not in self._sessions:
            self._sessions[device_id] = SessionSandbox(
                session_id=device_id,
                base_dir=self.base_dir,
            )
        return self._sessions[device_id]

    async def start_cleanup_task(self, interval_minutes: int = 30) -> None:
        """Start periodic cleanup of old sessions."""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(interval_minutes * 60)
                await self._cleanup_old_sessions()

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    async def _cleanup_old_sessions(self) -> None:
        """Remove sessions older than 4 hours."""
        cutoff = datetime.now() - timedelta(hours=4)
        to_remove = []

        for session_id, sandbox in self._sessions.items():
            if sandbox._created_at < cutoff:
                await sandbox.cleanup()
                to_remove.append(session_id)

        for session_id in to_remove:
            del self._sessions[session_id]

        if to_remove:
            logger.info("Cleaned up %d old sessions", len(to_remove))
```

---

## 4. WireGuard Peer Isolation

### Nuläge
Alla peers kan potentiellt kommunicera med varandra.

### Lösning: iptables på VPN-gateway

```bash
# /etc/wireguard/iptables-rules.sh
#!/bin/bash

# WireGuard interface
WG_IF="wg0"
WG_NET="10.0.0.0/24"
SERVER_IP="10.0.0.10"

# Flush existing rules
iptables -F FORWARD

# Allow established connections
iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow peers to reach server only
iptables -A FORWARD -i $WG_IF -d $SERVER_IP -j ACCEPT

# Block peer-to-peer communication
iptables -A FORWARD -i $WG_IF -o $WG_IF -j DROP

# Log dropped packets (optional)
iptables -A FORWARD -i $WG_IF -j LOG --log-prefix "WG-BLOCKED: "
iptables -A FORWARD -i $WG_IF -j DROP

echo "WireGuard peer isolation enabled"
```

**Lägg till i PostUp i wg0.conf:**
```ini
[Interface]
Address = 10.0.0.1/24
PrivateKey = ...
ListenPort = 51820
PostUp = /etc/wireguard/iptables-rules.sh
PostDown = iptables -F FORWARD
```

---

## 5. Implementation Ordning

### Fas 1: Ollama (1-2 timmar)
1. [ ] Skapa `scripts/ollama_setup.sh`
2. [ ] Uppdatera `config.py` med OLLAMA_CONFIG
3. [ ] Dokumentera i README

### Fas 2: Job Queue (4-6 timmar)
1. [ ] Skapa `src/agentfarm/queue/__init__.py`
2. [ ] Skapa `src/agentfarm/queue/job_queue.py`
3. [ ] Integrera i `web/server.py`
4. [ ] Lägg till WebSocket events för kö-status
5. [ ] Uppdatera frontend med kö-indikator

### Fas 3: Session Sandbox (2-3 timmar)
1. [ ] Lägg till `SessionSandbox` i `tools/sandbox.py`
2. [ ] Lägg till `SandboxManager`
3. [ ] Integrera i workflow-funktioner
4. [ ] Testa isolering

### Fas 4: WireGuard (1 timme)
1. [ ] Skapa iptables-script
2. [ ] Uppdatera wg0.conf
3. [ ] Testa att peers inte kan pinga varandra

---

## Tidsuppskattning

| Fas | Tid | Prioritet |
|-----|-----|-----------|
| Ollama config | 1-2h | 🔴 Kritisk |
| Job Queue | 4-6h | 🔴 Kritisk |
| Session Sandbox | 2-3h | 🟡 Hög |
| WireGuard isolation | 1h | 🟢 Medium |
| **Totalt** | **8-12h** | |

---

*Skapad: 2026-01-20*
