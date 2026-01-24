"""Tests for web server download functionality."""

import io
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

# Import the handler directly
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestZipDownload(AioHTTPTestCase):
    """Test cases for ZIP download functionality."""

    async def get_application(self):
        """Create test application with download route."""
        from agentfarm.web.server import api_project_download_zip_handler

        app = web.Application()
        app.router.add_get('/api/projects/download-zip', api_project_download_zip_handler)
        return app

    async def test_zip_download_success(self):
        """Test successful ZIP download."""
        # Create a temp project directory in ~/nya projekt/
        projects_base = Path.home() / "nya projekt"
        projects_base.mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory(dir=projects_base) as temp_dir:
            project_path = Path(temp_dir)

            # Create some test files
            (project_path / "main.py").write_text("print('hello')")
            (project_path / "utils.py").write_text("def util(): pass")
            (project_path / "README.md").write_text("# Test Project")

            # Also create a subdirectory
            subdir = project_path / "src"
            subdir.mkdir()
            (subdir / "app.py").write_text("# app code")

            # Request ZIP download
            resp = await self.client.request(
                "GET",
                f"/api/projects/download-zip?path={project_path}"
            )

            assert resp.status == 200
            assert resp.content_type == "application/zip"

            # Read and verify ZIP contents
            zip_data = await resp.read()
            zip_buffer = io.BytesIO(zip_data)

            with zipfile.ZipFile(zip_buffer, 'r') as zipf:
                names = zipf.namelist()
                assert "main.py" in names
                assert "utils.py" in names
                assert "README.md" in names
                assert "src/app.py" in names

                # Verify content
                assert zipf.read("main.py").decode() == "print('hello')"

    async def test_zip_download_excludes_hidden_files(self):
        """Test that hidden files are excluded from ZIP."""
        projects_base = Path.home() / "nya projekt"
        projects_base.mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory(dir=projects_base) as temp_dir:
            project_path = Path(temp_dir)

            # Create visible and hidden files
            (project_path / "main.py").write_text("visible")
            (project_path / ".hidden").write_text("hidden")
            (project_path / ".git").mkdir()
            (project_path / ".git" / "config").write_text("git config")

            resp = await self.client.request(
                "GET",
                f"/api/projects/download-zip?path={project_path}"
            )

            assert resp.status == 200

            zip_data = await resp.read()
            zip_buffer = io.BytesIO(zip_data)

            with zipfile.ZipFile(zip_buffer, 'r') as zipf:
                names = zipf.namelist()
                assert "main.py" in names
                assert ".hidden" not in names
                assert ".git/config" not in names

    async def test_zip_download_excludes_pycache(self):
        """Test that __pycache__ is excluded from ZIP."""
        projects_base = Path.home() / "nya projekt"
        projects_base.mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory(dir=projects_base) as temp_dir:
            project_path = Path(temp_dir)

            (project_path / "main.py").write_text("code")
            pycache = project_path / "__pycache__"
            pycache.mkdir()
            (pycache / "main.cpython-310.pyc").write_bytes(b"bytecode")

            resp = await self.client.request(
                "GET",
                f"/api/projects/download-zip?path={project_path}"
            )

            assert resp.status == 200

            zip_data = await resp.read()
            zip_buffer = io.BytesIO(zip_data)

            with zipfile.ZipFile(zip_buffer, 'r') as zipf:
                names = zipf.namelist()
                assert "main.py" in names
                assert "__pycache__/main.cpython-310.pyc" not in names

    async def test_zip_download_no_path(self):
        """Test error when no path provided."""
        resp = await self.client.request("GET", "/api/projects/download-zip")
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data

    async def test_zip_download_invalid_path(self):
        """Test error when path doesn't exist."""
        resp = await self.client.request(
            "GET",
            "/api/projects/download-zip?path=/nonexistent/path"
        )
        # Should return 403 (access denied) or 404 (not found)
        assert resp.status in (403, 404)

    async def test_zip_download_security_block(self):
        """Test that paths outside projects directory are blocked."""
        # Try to access /tmp (outside ~/nya projekt/)
        resp = await self.client.request(
            "GET",
            "/api/projects/download-zip?path=/tmp"
        )
        assert resp.status == 403
        data = await resp.json()
        assert "Access denied" in data.get("error", "")

    async def test_zip_download_empty_project(self):
        """Test ZIP download for empty project directory."""
        projects_base = Path.home() / "nya projekt"
        projects_base.mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory(dir=projects_base) as temp_dir:
            project_path = Path(temp_dir)

            resp = await self.client.request(
                "GET",
                f"/api/projects/download-zip?path={project_path}"
            )

            assert resp.status == 200

            zip_data = await resp.read()
            zip_buffer = io.BytesIO(zip_data)

            with zipfile.ZipFile(zip_buffer, 'r') as zipf:
                names = zipf.namelist()
                assert len(names) == 0  # Empty ZIP


class TestZipDownloadIntegration:
    """Integration tests for full workflow ZIP creation."""

    def test_zip_content_structure(self, tmp_path):
        """Test that ZIP maintains correct directory structure."""
        # Simulate a typical project structure
        project = tmp_path / "test-project"
        project.mkdir()

        # Create typical AgentFarm output structure
        (project / "main.py").write_text("# Main file")
        (project / "requirements.txt").write_text("pygame==2.5.0")

        src = project / "src"
        src.mkdir()
        (src / "game.py").write_text("# Game code")
        (src / "utils.py").write_text("# Utils")

        assets = project / "assets"
        assets.mkdir()
        (assets / "player.png").write_bytes(b"PNG data here")

        # Create ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in project.rglob('*'):
                if file_path.is_file():
                    arcname = str(file_path.relative_to(project))
                    zipf.write(file_path, arcname)

        # Verify structure
        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, 'r') as zipf:
            names = sorted(zipf.namelist())
            assert names == [
                "assets/player.png",
                "main.py",
                "requirements.txt",
                "src/game.py",
                "src/utils.py",
            ]

    def test_zip_binary_files(self, tmp_path):
        """Test that binary files are correctly included in ZIP."""
        project = tmp_path / "binary-test"
        project.mkdir()

        # Create a PNG-like file
        png_header = b'\x89PNG\r\n\x1a\n'
        (project / "image.png").write_bytes(png_header + b'\x00' * 100)

        # Create ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in project.rglob('*'):
                if file_path.is_file():
                    zipf.write(file_path, file_path.name)

        # Verify binary content preserved
        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, 'r') as zipf:
            content = zipf.read("image.png")
            assert content.startswith(png_header)
            assert len(content) == 108


class TestExistingProjectDownload(AioHTTPTestCase):
    """Test downloading actual existing projects."""

    async def get_application(self):
        """Create test application with download route."""
        from agentfarm.web.server import api_project_download_zip_handler

        app = web.Application()
        app.router.add_get('/api/projects/download-zip', api_project_download_zip_handler)
        return app

    async def test_download_existing_frog_project(self):
        """Test downloading the actual frog game project if it exists."""
        frog_project = Path.home() / "nya projekt" / "hoppegroda-skapa-ett"

        if not frog_project.exists():
            pytest.skip("Frog project not found - skipping real project test")

        resp = await self.client.request(
            "GET",
            f"/api/projects/download-zip?path={frog_project}"
        )

        assert resp.status == 200
        assert resp.content_type == "application/zip"

        # Verify ZIP is valid and contains expected files
        zip_data = await resp.read()
        assert len(zip_data) > 0, "ZIP should not be empty"

        zip_buffer = io.BytesIO(zip_data)
        with zipfile.ZipFile(zip_buffer, 'r') as zipf:
            names = zipf.namelist()
            # Should have some Python files
            py_files = [n for n in names if n.endswith('.py')]
            assert len(py_files) > 0, "Project should contain Python files"

            # Hidden files should be excluded
            assert not any(n.startswith('.') for n in names), "Hidden files should be excluded"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
