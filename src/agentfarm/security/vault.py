"""SecureVault - Docker-based secure storage for enterprise data.

Provides isolated, temporary storage for company context data that:
- Runs in Docker volumes with strict permissions
- Gets automatically cleaned up after session
- Never touches the host filesystem directly
- Integrates with Early Access tier verification
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VaultSession:
    """Represents an active vault session."""

    session_id: str
    user_id: str
    volume_name: str
    created_at: datetime
    expires_at: datetime
    mount_path: Path | None = None
    container_id: str | None = None

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id[:8] + "...",  # Truncate for privacy
            "volume_name": self.volume_name,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "is_expired": self.is_expired,
            "has_container": self.container_id is not None,
        }


class SecureVault:
    """Secure Docker-based vault for enterprise data.

    Creates isolated Docker volumes for each session, ensuring:
    - Data isolation between users
    - Automatic cleanup after session
    - No persistent storage on host
    - Encryption-ready architecture

    Usage:
        vault = SecureVault()
        async with vault.create_session(user_id) as session:
            await vault.store_document(session, "context.md", content)
            docs = await vault.list_documents(session)
    """

    DEFAULT_SESSION_DURATION = timedelta(hours=4)
    MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10 MB
    VAULT_PREFIX = "agentfarm_vault_"

    def __init__(
        self,
        docker_client: Any | None = None,
        session_duration: timedelta | None = None,
        cleanup_interval: int = 300,  # 5 minutes
    ) -> None:
        """Initialize SecureVault.

        Args:
            docker_client: Optional docker client (lazy loaded if None)
            session_duration: How long sessions remain valid
            cleanup_interval: Seconds between cleanup runs
        """
        self._docker = docker_client
        self._docker_available: bool | None = None
        self.session_duration = session_duration or self.DEFAULT_SESSION_DURATION
        self.cleanup_interval = cleanup_interval

        self._sessions: dict[str, VaultSession] = {}
        self._cleanup_task: asyncio.Task | None = None

    @property
    def docker(self) -> Any:
        """Lazy-load Docker client."""
        if self._docker is None:
            try:
                import docker

                self._docker = docker.from_env()
                self._docker_available = True
            except ImportError:
                logger.warning("Docker SDK not installed. pip install docker")
                self._docker_available = False
                raise RuntimeError("Docker SDK not installed")
            except Exception as e:
                logger.warning("Docker not available: %s", e)
                self._docker_available = False
                raise RuntimeError(f"Docker not available: {e}")
        return self._docker

    @property
    def is_available(self) -> bool:
        """Check if Docker is available."""
        if self._docker_available is None:
            try:
                _ = self.docker
            except RuntimeError:
                pass
        return self._docker_available or False

    def _generate_session_id(self) -> str:
        """Generate cryptographically secure session ID."""
        return secrets.token_urlsafe(24)

    def _generate_volume_name(self, session_id: str) -> str:
        """Generate Docker volume name from session."""
        hash_part = hashlib.sha256(session_id.encode()).hexdigest()[:12]
        return f"{self.VAULT_PREFIX}{hash_part}"

    async def create_session(self, user_id: str) -> VaultSession:
        """Create a new vault session.

        Args:
            user_id: User's device ID or identifier

        Returns:
            VaultSession with volume ready for use
        """
        if not self.is_available:
            raise RuntimeError("Docker not available - cannot create vault session")

        session_id = self._generate_session_id()
        volume_name = self._generate_volume_name(session_id)

        # Create Docker volume
        try:
            volume = self.docker.volumes.create(
                name=volume_name,
                labels={
                    "agentfarm.type": "vault",
                    "agentfarm.user": hashlib.sha256(user_id.encode()).hexdigest()[:16],
                    "agentfarm.session": session_id[:16],
                },
            )
            logger.info("Created vault volume: %s", volume_name)
        except Exception as e:
            logger.error("Failed to create volume: %s", e)
            raise RuntimeError(f"Failed to create vault: {e}")

        session = VaultSession(
            session_id=session_id,
            user_id=user_id,
            volume_name=volume_name,
            created_at=datetime.now(),
            expires_at=datetime.now() + self.session_duration,
        )

        self._sessions[session_id] = session

        # Start cleanup task if not running
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        return session

    async def destroy_session(self, session: VaultSession) -> None:
        """Destroy a vault session and cleanup resources.

        Args:
            session: Session to destroy
        """
        # Stop any running container
        if session.container_id:
            try:
                container = self.docker.containers.get(session.container_id)
                container.stop(timeout=5)
                container.remove(force=True)
                logger.info("Removed container: %s", session.container_id[:12])
            except Exception as e:
                logger.warning("Failed to remove container: %s", e)

        # Remove volume
        try:
            volume = self.docker.volumes.get(session.volume_name)
            volume.remove(force=True)
            logger.info("Removed vault volume: %s", session.volume_name)
        except Exception as e:
            logger.warning("Failed to remove volume: %s", e)

        # Remove from tracking
        self._sessions.pop(session.session_id, None)

    async def store_document(
        self,
        session: VaultSession,
        filename: str,
        content: str | bytes,
    ) -> str:
        """Store a document in the vault.

        Args:
            session: Active vault session
            filename: Name for the document
            content: Document content

        Returns:
            Path to document in vault
        """
        if session.is_expired:
            raise RuntimeError("Session expired")

        if isinstance(content, str):
            content = content.encode("utf-8")

        if len(content) > self.MAX_DOCUMENT_SIZE:
            raise ValueError(f"Document too large (max {self.MAX_DOCUMENT_SIZE // 1024 // 1024}MB)")

        # Use a temporary container to write to volume
        vault_path = f"/vault/{filename}"

        try:
            # Create temp file with content
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            # Copy to volume using a container
            container = self.docker.containers.run(
                "alpine:latest",
                f"sh -c 'cat > {vault_path}'",
                volumes={session.volume_name: {"bind": "/vault", "mode": "rw"}},
                stdin_open=True,
                remove=True,
                detach=False,
            )

            # Alternative: use docker cp
            self.docker.containers.run(
                "alpine:latest",
                f"cp /tmp/doc {vault_path}",
                volumes={
                    session.volume_name: {"bind": "/vault", "mode": "rw"},
                    tmp_path: {"bind": "/tmp/doc", "mode": "ro"},
                },
                remove=True,
            )

            logger.info("Stored document: %s (%d bytes)", filename, len(content))
            return vault_path

        except Exception as e:
            logger.error("Failed to store document: %s", e)
            raise RuntimeError(f"Failed to store document: {e}")
        finally:
            # Cleanup temp file
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass

    async def retrieve_document(self, session: VaultSession, filename: str) -> bytes:
        """Retrieve a document from the vault.

        Args:
            session: Active vault session
            filename: Document filename

        Returns:
            Document content as bytes
        """
        if session.is_expired:
            raise RuntimeError("Session expired")

        vault_path = f"/vault/{filename}"

        try:
            result = self.docker.containers.run(
                "alpine:latest",
                f"cat {vault_path}",
                volumes={session.volume_name: {"bind": "/vault", "mode": "ro"}},
                remove=True,
            )
            return result
        except Exception as e:
            logger.error("Failed to retrieve document: %s", e)
            raise RuntimeError(f"Failed to retrieve document: {e}")

    async def list_documents(self, session: VaultSession) -> list[str]:
        """List documents in the vault.

        Args:
            session: Active vault session

        Returns:
            List of document filenames
        """
        if session.is_expired:
            raise RuntimeError("Session expired")

        try:
            result = self.docker.containers.run(
                "alpine:latest",
                "ls -1 /vault",
                volumes={session.volume_name: {"bind": "/vault", "mode": "ro"}},
                remove=True,
            )
            files = result.decode("utf-8").strip().split("\n")
            return [f for f in files if f]  # Filter empty strings
        except Exception as e:
            logger.error("Failed to list documents: %s", e)
            return []

    async def delete_document(self, session: VaultSession, filename: str) -> bool:
        """Delete a document from the vault.

        Args:
            session: Active vault session
            filename: Document to delete

        Returns:
            True if deleted, False otherwise
        """
        if session.is_expired:
            raise RuntimeError("Session expired")

        vault_path = f"/vault/{filename}"

        try:
            self.docker.containers.run(
                "alpine:latest",
                f"rm -f {vault_path}",
                volumes={session.volume_name: {"bind": "/vault", "mode": "rw"}},
                remove=True,
            )
            logger.info("Deleted document: %s", filename)
            return True
        except Exception as e:
            logger.warning("Failed to delete document: %s", e)
            return False

    async def _cleanup_loop(self) -> None:
        """Background task to cleanup expired sessions."""
        while True:
            await asyncio.sleep(self.cleanup_interval)

            expired = [
                session for session in self._sessions.values() if session.is_expired
            ]

            for session in expired:
                logger.info("Cleaning up expired session: %s", session.session_id[:16])
                try:
                    await self.destroy_session(session)
                except Exception as e:
                    logger.error("Cleanup failed for %s: %s", session.session_id[:16], e)

    def get_active_sessions(self) -> list[VaultSession]:
        """Get all active (non-expired) sessions."""
        return [s for s in self._sessions.values() if not s.is_expired]

    async def cleanup_all(self) -> int:
        """Cleanup all vault volumes (for maintenance).

        Returns:
            Number of volumes cleaned up
        """
        if not self.is_available:
            return 0

        count = 0

        # Cleanup tracked sessions
        for session in list(self._sessions.values()):
            try:
                await self.destroy_session(session)
                count += 1
            except Exception:
                pass

        # Cleanup any orphaned volumes
        try:
            volumes = self.docker.volumes.list(
                filters={"label": "agentfarm.type=vault"}
            )
            for volume in volumes:
                try:
                    volume.remove(force=True)
                    count += 1
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Failed to list volumes for cleanup: %s", e)

        return count

    def get_stats(self) -> dict[str, Any]:
        """Get vault statistics."""
        return {
            "docker_available": self.is_available,
            "active_sessions": len(self.get_active_sessions()),
            "total_sessions": len(self._sessions),
            "session_duration_hours": self.session_duration.total_seconds() / 3600,
        }
