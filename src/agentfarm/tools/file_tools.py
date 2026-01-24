from __future__ import annotations

"""File operation tools for agents."""

import os
from pathlib import Path

import aiofiles


class FileTools:
    """File operations for agents.

    Provides read, write, edit, list, and search operations.
    All paths are validated against the working directory for security.
    """

    def __init__(self, working_dir: str = ".") -> None:
        self.working_dir = Path(working_dir).resolve()

    def _validate_path(self, path: str) -> Path:
        """Validate and resolve path within working directory."""
        resolved = (self.working_dir / path).resolve()
        if not str(resolved).startswith(str(self.working_dir)):
            raise ValueError(f"Path {path} is outside working directory")
        return resolved

    async def read_file(self, path: str, **kwargs) -> str:
        """Read contents of a file."""
        file_path = self._validate_path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            return await f.read()

    async def write_file(self, path: str, content: str, **kwargs) -> str:
        """Write content to a file (create or overwrite)."""
        file_path = self._validate_path(path)

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)

        return f"Wrote {len(content)} bytes to {path}"

    async def edit_file(self, path: str, old_content: str, new_content: str, **kwargs) -> str:
        """Replace old_content with new_content in a file.

        If old_content is empty and file doesn't exist, creates the file.
        """
        file_path = self._validate_path(path)

        # Special case: empty old_content means create new file
        if not old_content or old_content.strip() == "":
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(new_content)
            return f"Created {path}"

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path} (resolved: {file_path})")

        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()

        if old_content not in content:
            # Try fuzzy match: normalize whitespace
            match_result = self._fuzzy_find(content, old_content)
            if match_result:
                actual_old, start, end = match_result
                new_file_content = content[:start] + new_content + content[end:]
                async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                    await f.write(new_file_content)
                return f"Edited {path} (fuzzy match)"
            raise ValueError(
                f"Content to replace not found in {path}. "
                f"First 50 chars of search: {old_content[:50]!r}..."
            )

        new_file_content = content.replace(old_content, new_content, 1)

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(new_file_content)

        return f"Edited {path}"

    async def list_directory(self, path: str = ".", **kwargs) -> str:
        """List contents of a directory."""
        dir_path = self._validate_path(path)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        entries = []
        for entry in sorted(dir_path.iterdir()):
            prefix = "d " if entry.is_dir() else "f "
            relative = entry.relative_to(self.working_dir)
            entries.append(f"{prefix}{relative}")

        return "\n".join(entries) if entries else "(empty directory)"

    async def search_code(self, pattern: str, path: str = ".", **kwargs) -> str:
        """Search for pattern in files (simple grep-like)."""
        search_path = self._validate_path(path)
        results: list[str] = []

        def search_file(file_path: Path) -> list[str]:
            matches = []
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if pattern in line:
                            relative = file_path.relative_to(self.working_dir)
                            matches.append(f"{relative}:{i}: {line.strip()}")
            except (OSError, UnicodeDecodeError):
                pass
            return matches

        if search_path.is_file():
            results.extend(search_file(search_path))
        else:
            for root, _, files in os.walk(search_path):
                for file in files:
                    if file.endswith((".py", ".js", ".ts", ".md", ".txt", ".yaml", ".json")):
                        file_path = Path(root) / file
                        results.extend(search_file(file_path))
                        if len(results) > 100:
                            break
                if len(results) > 100:
                    break

        if not results:
            return f"No matches found for '{pattern}'"

        return "\n".join(results[:100])

    def _fuzzy_find(self, content: str, search: str) -> tuple[str, int, int] | None:
        """Find content with fuzzy whitespace matching.

        Args:
            content: The file content to search in
            search: The pattern to search for

        Returns:
            Tuple of (matched_text, start_index, end_index) or None if not found
        """
        import re
        # 1. Normalize whitespace FIRST (collapse multiple spaces/newlines to single space)
        search_normalized = re.sub(r'\s+', ' ', search.strip())
        # 2. Escape special regex characters
        search_escaped = re.escape(search_normalized)
        # 3. Replace the escaped single space with flexible whitespace pattern
        search_pattern = search_escaped.replace(r'\ ', r'\s+')

        match = re.search(search_pattern, content, re.DOTALL)
        if match:
            return match.group(0), match.start(), match.end()
        return None

    async def file_exists(self, path: str) -> bool:
        """Check if a file exists."""
        try:
            file_path = self._validate_path(path)
            return file_path.exists()
        except ValueError:
            return False

    async def delete_file(self, path: str) -> str:
        """Delete a file."""
        file_path = self._validate_path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if file_path.is_dir():
            raise IsADirectoryError(f"Cannot delete directory with delete_file: {path}")

        file_path.unlink()
        return f"Deleted {path}"
