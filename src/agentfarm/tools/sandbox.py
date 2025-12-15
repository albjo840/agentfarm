from __future__ import annotations

"""Docker sandbox for safe code execution."""

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
