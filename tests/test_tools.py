"""Tests for tools."""

import os
import tempfile
from pathlib import Path

import pytest

from agentfarm.tools.file_tools import FileTools


class TestFileTools:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def file_tools(self, temp_dir):
        return FileTools(temp_dir)

    @pytest.mark.asyncio
    async def test_write_and_read_file(self, file_tools, temp_dir):
        await file_tools.write_file("test.txt", "hello world")
        content = await file_tools.read_file("test.txt")
        assert content == "hello world"

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, file_tools):
        with pytest.raises(FileNotFoundError):
            await file_tools.read_file("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_edit_file(self, file_tools, temp_dir):
        await file_tools.write_file("test.txt", "hello world")
        await file_tools.edit_file("test.txt", "world", "python")
        content = await file_tools.read_file("test.txt")
        assert content == "hello python"

    @pytest.mark.asyncio
    async def test_edit_file_content_not_found(self, file_tools, temp_dir):
        await file_tools.write_file("test.txt", "hello world")
        with pytest.raises(ValueError):
            await file_tools.edit_file("test.txt", "nonexistent", "new")

    @pytest.mark.asyncio
    async def test_list_directory(self, file_tools, temp_dir):
        await file_tools.write_file("a.txt", "a")
        await file_tools.write_file("b.txt", "b")
        listing = await file_tools.list_directory(".")
        assert "a.txt" in listing
        assert "b.txt" in listing

    @pytest.mark.asyncio
    async def test_search_code(self, file_tools, temp_dir):
        await file_tools.write_file("main.py", "def hello():\n    print('hi')")
        results = await file_tools.search_code("hello", ".")
        assert "main.py" in results
        assert "def hello" in results

    @pytest.mark.asyncio
    async def test_search_no_results(self, file_tools, temp_dir):
        await file_tools.write_file("main.py", "def hello():\n    pass")
        results = await file_tools.search_code("nonexistent_pattern", ".")
        assert "No matches found" in results

    @pytest.mark.asyncio
    async def test_file_exists(self, file_tools, temp_dir):
        await file_tools.write_file("exists.txt", "content")
        assert await file_tools.file_exists("exists.txt")
        assert not await file_tools.file_exists("not_exists.txt")

    @pytest.mark.asyncio
    async def test_delete_file(self, file_tools, temp_dir):
        await file_tools.write_file("to_delete.txt", "content")
        assert await file_tools.file_exists("to_delete.txt")
        await file_tools.delete_file("to_delete.txt")
        assert not await file_tools.file_exists("to_delete.txt")

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, file_tools, temp_dir):
        with pytest.raises(ValueError):
            await file_tools.read_file("../../../etc/passwd")

    @pytest.mark.asyncio
    async def test_write_creates_directories(self, file_tools, temp_dir):
        await file_tools.write_file("nested/dir/file.txt", "content")
        content = await file_tools.read_file("nested/dir/file.txt")
        assert content == "content"
