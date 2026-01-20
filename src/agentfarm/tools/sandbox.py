from __future__ import annotations

"""Docker sandbox for safe code execution.

Provides two sandbox types:
- SandboxRunner: Basic sandbox with read-only working directory
- SessionSandbox: Per-user isolated sandbox with unique volumes

Session isolation ensures:
- User A cannot see User B's files
- Each session gets a unique Docker volume
- Automatic cleanup after 4 hours of inactivity
"""

import asyncio
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import docker
    from docker.errors import DockerException

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None  # type: ignore
    DockerException = Exception  # type: ignore


@dataclass
class SandboxResult:
    """Result from sandbox execution."""

    success: bool
    output: str
    error: str | None
    exit_code: int
    duration_ms: int


class SandboxRunner:
    """Docker-based sandbox for safe code execution.

    Runs untrusted code in an isolated container with:
    - No network access
    - Limited CPU and memory
    - Read-only filesystem (except /tmp)
    - Timeout enforcement
    """

    DEFAULT_IMAGE = "python:3.11-slim"
    DEFAULT_TIMEOUT = 30
    DEFAULT_MEMORY = "256m"
    DEFAULT_CPU = 0.5

    def __init__(
        self,
        working_dir: str = ".",
        image: str = DEFAULT_IMAGE,
        timeout: int = DEFAULT_TIMEOUT,
        memory: str = DEFAULT_MEMORY,
        cpu_limit: float = DEFAULT_CPU,
    ) -> None:
        self.working_dir = Path(working_dir).resolve()
        self.image = image
        self.timeout = timeout
        self.memory = memory
        self.cpu_limit = cpu_limit
        self._client: Any = None

    def _get_client(self) -> Any:
        """Get or create Docker client."""
        if not DOCKER_AVAILABLE:
            raise RuntimeError(
                "Docker package not installed. Install with: pip install docker"
            )

        if self._client is None:
            try:
                self._client = docker.from_env()
                self._client.ping()
            except DockerException as e:
                raise RuntimeError(f"Cannot connect to Docker: {e}") from e

        return self._client

    async def run(
        self,
        command: str,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        """Run a command in the sandbox.

        Args:
            command: Command to execute
            timeout: Override default timeout
            env: Environment variables

        Returns:
            Output from the command
        """
        result = await self.run_with_result(command, timeout, env)
        if result.error:
            return f"Error: {result.error}\n{result.output}"
        return result.output

    async def run_with_result(
        self,
        command: str,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run command and return detailed result."""
        timeout = timeout or self.timeout

        # Run in thread pool since docker SDK is sync
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._run_sync,
            command,
            timeout,
            env or {},
        )

    def _run_sync(
        self,
        command: str,
        timeout: int,
        env: dict[str, str],
    ) -> SandboxResult:
        """Synchronous sandbox execution."""
        client = self._get_client()
        container_name = f"agentfarm-sandbox-{uuid.uuid4().hex[:8]}"

        try:
            # Create container with security constraints
            container = client.containers.create(
                image=self.image,
                command=["sh", "-c", command],
                name=container_name,
                working_dir="/workspace",
                volumes={
                    str(self.working_dir): {
                        "bind": "/workspace",
                        "mode": "ro",  # Read-only mount
                    }
                },
                environment=env,
                network_mode="none",  # No network access
                mem_limit=self.memory,
                nano_cpus=int(self.cpu_limit * 1e9),
                read_only=True,
                tmpfs={"/tmp": "size=64m"},  # Writable /tmp
                security_opt=["no-new-privileges"],
            )

            # Start and wait
            container.start()

            try:
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", -1)
            except Exception:
                container.kill()
                return SandboxResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout}s",
                    exit_code=-1,
                    duration_ms=timeout * 1000,
                )

            # Get logs
            logs = container.logs(stdout=True, stderr=True).decode(
                "utf-8", errors="replace"
            )

            return SandboxResult(
                success=exit_code == 0,
                output=logs,
                error=None if exit_code == 0 else f"Exit code: {exit_code}",
                exit_code=exit_code,
                duration_ms=0,
            )

        except DockerException as e:
            return SandboxResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                duration_ms=0,
            )
        finally:
            # Cleanup
            try:
                container = client.containers.get(container_name)
                container.remove(force=True)
            except Exception:
                pass

    async def run_python(self, code: str, timeout: int | None = None) -> str:
        """Run Python code in sandbox."""
        # Escape the code for shell
        escaped = code.replace("'", "'\"'\"'")
        command = f"python -c '{escaped}'"
        return await self.run(command, timeout)

    async def run_script(
        self,
        script_path: str,
        args: list[str] | None = None,
        timeout: int | None = None,
    ) -> str:
        """Run a script file in sandbox."""
        args_str = " ".join(args) if args else ""
        command = f"python /workspace/{script_path} {args_str}"
        return await self.run(command, timeout)

    def is_available(self) -> bool:
        """Check if Docker sandbox is available."""
        if not DOCKER_AVAILABLE:
            return False
        try:
            self._get_client()
            return True
        except RuntimeError:
            return False

    async def ensure_image(self) -> str:
        """Ensure the sandbox image is available."""
        if not DOCKER_AVAILABLE:
            return "Docker not available"

        client = self._get_client()
        try:
            client.images.get(self.image)
            return f"Image {self.image} ready"
        except docker.errors.ImageNotFound:
            client.images.pull(self.image)
            return f"Pulled image {self.image}"


class SessionSandbox(SandboxRunner):
    """Per-session isolated sandbox with unique volumes.

    Each user/device gets their own isolated directory that:
    - Is read-write (so agents can create files)
    - Is completely separate from other users
    - Gets cleaned up after max_age_hours of inactivity

    Usage:
        sandbox = SessionSandbox(
            session_id="user123",
            base_dir=Path("/var/agentfarm"),
        )
        result = await sandbox.run("python script.py")
        await sandbox.cleanup()  # When done
    """

    def __init__(
        self,
        session_id: str,
        base_dir: Path,
        image: str = SandboxRunner.DEFAULT_IMAGE,
        timeout: int = SandboxRunner.DEFAULT_TIMEOUT,
        memory: str = "512m",  # More memory for real work
        cpu_limit: float = 1.0,  # Full CPU for sessions
        max_age_hours: int = 4,
    ) -> None:
        """Initialize session sandbox.

        Args:
            session_id: Unique session identifier (e.g., device_id)
            base_dir: Base directory for all sessions
            image: Docker image to use
            timeout: Default command timeout
            memory: Memory limit (default 512m for sessions)
            cpu_limit: CPU limit (default 1.0 for sessions)
            max_age_hours: Auto-cleanup after this many hours
        """
        self.session_id = session_id
        self.base_dir = Path(base_dir)
        self.max_age_hours = max_age_hours

        # Create unique session directory
        # Use first 16 chars of session_id for shorter paths
        safe_id = "".join(c for c in session_id[:16] if c.isalnum())
        self.session_dir = self.base_dir / ".sessions" / safe_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Track creation time for cleanup
        self.created_at = datetime.now()
        self.last_activity = datetime.now()

        # Initialize parent with session directory as working_dir
        super().__init__(
            working_dir=str(self.session_dir),
            image=image,
            timeout=timeout,
            memory=memory,
            cpu_limit=cpu_limit,
        )

        logger.info("Session sandbox created: %s at %s", session_id[:8], self.session_dir)

    def _run_sync(
        self,
        command: str,
        timeout: int,
        env: dict[str, str],
    ) -> SandboxResult:
        """Run with session-isolated read-write volume."""
        client = self._get_client()
        container_name = f"agentfarm-{self.session_id[:8]}-{uuid.uuid4().hex[:4]}"

        # Update last activity
        self.last_activity = datetime.now()

        try:
            # Create container with session-specific volume (read-write)
            container = client.containers.create(
                image=self.image,
                command=["sh", "-c", command],
                name=container_name,
                working_dir="/workspace",
                volumes={
                    str(self.session_dir): {
                        "bind": "/workspace",
                        "mode": "rw",  # Read-write for session
                    }
                },
                environment=env,
                network_mode="none",  # No network access
                mem_limit=self.memory,
                nano_cpus=int(self.cpu_limit * 1e9),
                # NOT read_only - session can write to /workspace
                tmpfs={"/tmp": "size=128m"},  # Larger tmp for sessions
                security_opt=["no-new-privileges"],
            )

            # Start and wait
            container.start()

            try:
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", -1)
            except Exception:
                container.kill()
                return SandboxResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout}s",
                    exit_code=-1,
                    duration_ms=timeout * 1000,
                )

            # Get logs
            logs = container.logs(stdout=True, stderr=True).decode(
                "utf-8", errors="replace"
            )

            return SandboxResult(
                success=exit_code == 0,
                output=logs,
                error=None if exit_code == 0 else f"Exit code: {exit_code}",
                exit_code=exit_code,
                duration_ms=0,
            )

        except DockerException as e:
            return SandboxResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                duration_ms=0,
            )
        finally:
            # Cleanup container (but keep session directory)
            try:
                container = client.containers.get(container_name)
                container.remove(force=True)
            except Exception:
                pass

    def is_expired(self) -> bool:
        """Check if session has expired based on last activity."""
        cutoff = datetime.now() - timedelta(hours=self.max_age_hours)
        return self.last_activity < cutoff

    def get_files(self) -> list[dict[str, Any]]:
        """List files in session directory."""
        files = []
        if self.session_dir.exists():
            for path in self.session_dir.rglob("*"):
                if path.is_file():
                    rel_path = path.relative_to(self.session_dir)
                    files.append({
                        "path": str(rel_path),
                        "size": path.stat().st_size,
                        "modified": datetime.fromtimestamp(
                            path.stat().st_mtime
                        ).isoformat(),
                    })
        return files

    async def cleanup(self) -> None:
        """Delete session directory and all files."""
        if self.session_dir.exists():
            try:
                shutil.rmtree(self.session_dir)
                logger.info("Session %s cleaned up", self.session_id[:8])
            except Exception as e:
                logger.warning("Failed to cleanup session %s: %s", self.session_id[:8], e)

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now()


class SandboxManager:
    """Manages session sandboxes with automatic cleanup.

    Features:
    - Creates isolated sandboxes per user/device
    - Tracks active sessions
    - Automatic cleanup of expired sessions (default 4 hours)
    - Statistics and monitoring

    Usage:
        manager = SandboxManager(base_dir=Path("/var/agentfarm"))
        await manager.start_cleanup_task()

        sandbox = await manager.get_sandbox("user123")
        result = await sandbox.run("python script.py")

        # Later, automatic cleanup removes inactive sessions
    """

    def __init__(
        self,
        base_dir: Path,
        max_age_hours: int = 4,
        cleanup_interval_minutes: int = 30,
    ) -> None:
        """Initialize sandbox manager.

        Args:
            base_dir: Base directory for all session sandboxes
            max_age_hours: Sessions expire after this many hours
            cleanup_interval_minutes: How often to check for expired sessions
        """
        self.base_dir = Path(base_dir)
        self.max_age_hours = max_age_hours
        self.cleanup_interval_minutes = cleanup_interval_minutes

        self._sessions: dict[str, SessionSandbox] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        # Ensure base directory exists
        sessions_dir = self.base_dir / ".sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "SandboxManager initialized: base=%s, max_age=%dh",
            self.base_dir,
            self.max_age_hours,
        )

    async def get_sandbox(self, session_id: str) -> SessionSandbox:
        """Get or create sandbox for a session.

        Args:
            session_id: Unique session identifier (e.g., device_id)

        Returns:
            SessionSandbox instance for this session
        """
        async with self._lock:
            if session_id in self._sessions:
                sandbox = self._sessions[session_id]
                sandbox.touch()  # Update activity
                return sandbox

            # Create new session sandbox
            sandbox = SessionSandbox(
                session_id=session_id,
                base_dir=self.base_dir,
                max_age_hours=self.max_age_hours,
            )
            self._sessions[session_id] = sandbox
            return sandbox

    async def remove_sandbox(self, session_id: str) -> bool:
        """Remove and cleanup a specific sandbox.

        Args:
            session_id: Session to remove

        Returns:
            True if removed, False if not found
        """
        async with self._lock:
            if session_id in self._sessions:
                sandbox = self._sessions[session_id]
                await sandbox.cleanup()
                del self._sessions[session_id]
                return True
            return False

    async def start_cleanup_task(self) -> None:
        """Start periodic cleanup of expired sessions."""
        if self._cleanup_task is not None:
            return

        async def cleanup_loop() -> None:
            while True:
                await asyncio.sleep(self.cleanup_interval_minutes * 60)
                await self._cleanup_expired()

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info(
            "Sandbox cleanup task started (interval=%d min)",
            self.cleanup_interval_minutes,
        )

    async def stop_cleanup_task(self) -> None:
        """Stop the cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_expired(self) -> None:
        """Remove sessions that have expired."""
        async with self._lock:
            expired = [
                session_id
                for session_id, sandbox in self._sessions.items()
                if sandbox.is_expired()
            ]

            for session_id in expired:
                sandbox = self._sessions[session_id]
                await sandbox.cleanup()
                del self._sessions[session_id]

            if expired:
                logger.info("Cleaned up %d expired sessions", len(expired))

    async def cleanup_all(self) -> int:
        """Cleanup all sessions (for shutdown)."""
        async with self._lock:
            count = len(self._sessions)
            for sandbox in self._sessions.values():
                await sandbox.cleanup()
            self._sessions.clear()
            logger.info("Cleaned up all %d sessions", count)
            return count

    def get_stats(self) -> dict[str, Any]:
        """Get manager statistics."""
        active_count = len(self._sessions)
        total_files = 0
        total_size = 0

        for sandbox in self._sessions.values():
            files = sandbox.get_files()
            total_files += len(files)
            total_size += sum(f["size"] for f in files)

        return {
            "active_sessions": active_count,
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_age_hours": self.max_age_hours,
            "cleanup_interval_minutes": self.cleanup_interval_minutes,
        }

    def get_session_info(self, session_id: str) -> dict[str, Any] | None:
        """Get info about a specific session."""
        if session_id not in self._sessions:
            return None

        sandbox = self._sessions[session_id]
        return {
            "session_id": session_id[:8],
            "created_at": sandbox.created_at.isoformat(),
            "last_activity": sandbox.last_activity.isoformat(),
            "is_expired": sandbox.is_expired(),
            "files": sandbox.get_files(),
            "path": str(sandbox.session_dir),
        }


# Global sandbox manager instance
_sandbox_manager: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager | None:
    """Get the global sandbox manager."""
    return _sandbox_manager


async def init_sandbox_manager(
    base_dir: Path,
    max_age_hours: int = 4,
    start_cleanup: bool = True,
) -> SandboxManager:
    """Initialize the global sandbox manager.

    Args:
        base_dir: Base directory for session sandboxes
        max_age_hours: Session expiry time
        start_cleanup: Whether to start cleanup task

    Returns:
        Initialized SandboxManager
    """
    global _sandbox_manager

    _sandbox_manager = SandboxManager(
        base_dir=base_dir,
        max_age_hours=max_age_hours,
    )

    if start_cleanup:
        await _sandbox_manager.start_cleanup_task()

    return _sandbox_manager


async def shutdown_sandbox_manager() -> None:
    """Shutdown and cleanup the global sandbox manager."""
    global _sandbox_manager

    if _sandbox_manager:
        await _sandbox_manager.stop_cleanup_task()
        await _sandbox_manager.cleanup_all()
        _sandbox_manager = None
