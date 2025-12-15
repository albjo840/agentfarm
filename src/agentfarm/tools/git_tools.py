from __future__ import annotations

"""Git operations for agents."""

import asyncio
from pathlib import Path


class GitTools:
    """Git operations for version control.

    Provides diff, status, commit, and branch operations.
    """

    def __init__(self, working_dir: str = ".") -> None:
        self.working_dir = Path(working_dir).resolve()

    async def _run_git(self, *args: str) -> tuple[int, str]:
        """Run a git command and return (returncode, output)."""
        cmd = ["git", *args]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n" + stderr.decode("utf-8", errors="replace")
            return proc.returncode or 0, output.strip()
        except FileNotFoundError:
            return -1, "git not found"

    async def status(self) -> str:
        """Get git status."""
        _, output = await self._run_git("status", "--short")
        return output or "(no changes)"

    async def get_diff(self, path: str = ".", base: str = "HEAD") -> str:
        """Get diff of changes."""
        _, output = await self._run_git("diff", base, "--", path)
        return output or "(no diff)"

    async def get_staged_diff(self) -> str:
        """Get diff of staged changes."""
        _, output = await self._run_git("diff", "--cached")
        return output or "(no staged changes)"

    async def add(self, *paths: str) -> str:
        """Stage files for commit."""
        if not paths:
            paths = (".",)
        returncode, output = await self._run_git("add", *paths)
        if returncode != 0:
            return f"Failed to stage: {output}"
        return f"Staged: {', '.join(paths)}"

    async def commit(self, message: str) -> str:
        """Create a commit."""
        returncode, output = await self._run_git("commit", "-m", message)
        if returncode != 0:
            return f"Commit failed: {output}"
        return output

    async def get_log(self, n: int = 5) -> str:
        """Get recent commit log."""
        _, output = await self._run_git(
            "log", f"-{n}", "--oneline", "--no-decorate"
        )
        return output

    async def get_branch(self) -> str:
        """Get current branch name."""
        _, output = await self._run_git("branch", "--show-current")
        return output or "HEAD"

    async def list_branches(self) -> str:
        """List all branches."""
        _, output = await self._run_git("branch", "-a")
        return output

    async def create_branch(self, name: str) -> str:
        """Create a new branch."""
        returncode, output = await self._run_git("checkout", "-b", name)
        if returncode != 0:
            return f"Failed to create branch: {output}"
        return f"Created and switched to branch: {name}"

    async def get_changed_files(self, base: str = "HEAD") -> list[str]:
        """Get list of changed files compared to base."""
        _, output = await self._run_git(
            "diff", "--name-only", base
        )
        return [f for f in output.split("\n") if f.strip()]

    async def get_file_at_ref(self, path: str, ref: str = "HEAD") -> str:
        """Get file contents at a specific ref."""
        returncode, output = await self._run_git("show", f"{ref}:{path}")
        if returncode != 0:
            return f"Error: {output}"
        return output

    async def is_git_repo(self) -> bool:
        """Check if working directory is a git repository."""
        returncode, _ = await self._run_git("rev-parse", "--git-dir")
        return returncode == 0

    async def init(self) -> str:
        """Initialize a new git repository."""
        returncode, output = await self._run_git("init")
        if returncode != 0:
            return f"Failed to init: {output}"
        return "Initialized git repository"
