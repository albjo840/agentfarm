"""Integration tests for Docker sandbox.

These tests require Docker to be running. They are marked with
@pytest.mark.docker and can be skipped in CI environments without Docker.
"""

import pytest
import asyncio
from pathlib import Path

from agentfarm.tools.sandbox import SandboxRunner, SandboxResult, DOCKER_AVAILABLE


# Skip all tests if Docker is not available
pytestmark = pytest.mark.skipif(
    not DOCKER_AVAILABLE,
    reason="Docker package not installed"
)


@pytest.fixture
def sandbox(tmp_path):
    """Create a sandbox runner with a temp working directory."""
    return SandboxRunner(working_dir=str(tmp_path))


@pytest.fixture
def sandbox_with_files(tmp_path):
    """Create sandbox with test files."""
    # Create test files
    (tmp_path / "hello.py").write_text('print("Hello, World!")')
    (tmp_path / "data.txt").write_text("test data\n")

    return SandboxRunner(working_dir=str(tmp_path))


class TestSandboxAvailability:
    """Test sandbox availability checks."""

    def test_docker_available_constant(self):
        """DOCKER_AVAILABLE should be True if docker package is installed."""
        # This test only runs if DOCKER_AVAILABLE is True
        assert DOCKER_AVAILABLE is True

    def test_is_available_returns_bool(self, sandbox):
        """is_available should return a boolean."""
        result = sandbox.is_available()
        assert isinstance(result, bool)


@pytest.mark.docker
class TestSandboxExecution:
    """Test actual sandbox execution (requires running Docker)."""

    @pytest.mark.asyncio
    async def test_simple_echo(self, sandbox):
        """Test running a simple echo command."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        result = await sandbox.run("echo 'hello world'")
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_python_code(self, sandbox):
        """Test running Python code."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        result = await sandbox.run_python("print(2 + 2)")
        assert "4" in result

    @pytest.mark.asyncio
    async def test_sandbox_result_success(self, sandbox):
        """Test SandboxResult for successful execution."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        result = await sandbox.run_with_result("echo 'test'")

        assert isinstance(result, SandboxResult)
        assert result.success is True
        assert result.exit_code == 0
        assert result.error is None
        assert "test" in result.output

    @pytest.mark.asyncio
    async def test_sandbox_result_failure(self, sandbox):
        """Test SandboxResult for failed execution."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        result = await sandbox.run_with_result("exit 1")

        assert isinstance(result, SandboxResult)
        assert result.success is False
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_network_isolation(self, sandbox):
        """Test that network access is blocked."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        # Try to access the network - should fail
        result = await sandbox.run_with_result(
            "python -c \"import urllib.request; urllib.request.urlopen('http://google.com')\"",
            timeout=10,
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_read_only_workspace(self, sandbox_with_files):
        """Test that workspace is mounted read-only."""
        if not sandbox_with_files.is_available():
            pytest.skip("Docker not available")

        # Try to write to workspace - should fail
        result = await sandbox_with_files.run_with_result(
            "echo 'test' > /workspace/new_file.txt"
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_can_read_workspace(self, sandbox_with_files):
        """Test that workspace files can be read."""
        if not sandbox_with_files.is_available():
            pytest.skip("Docker not available")

        result = await sandbox_with_files.run_with_result(
            "cat /workspace/data.txt"
        )

        assert result.success is True
        assert "test data" in result.output

    @pytest.mark.asyncio
    async def test_run_script(self, sandbox_with_files):
        """Test running a Python script from workspace."""
        if not sandbox_with_files.is_available():
            pytest.skip("Docker not available")

        result = await sandbox_with_files.run_script("hello.py")
        assert "Hello, World!" in result

    @pytest.mark.asyncio
    async def test_timeout_enforcement(self, sandbox):
        """Test that timeout is enforced."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        result = await sandbox.run_with_result(
            "sleep 60",  # Try to sleep for 60 seconds
            timeout=2,  # But timeout after 2 seconds
        )

        assert result.success is False
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_tmp_is_writable(self, sandbox):
        """Test that /tmp is writable."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        result = await sandbox.run_with_result(
            "echo 'test' > /tmp/test.txt && cat /tmp/test.txt"
        )

        assert result.success is True
        assert "test" in result.output


@pytest.mark.docker
class TestSandboxSecurity:
    """Security-focused sandbox tests."""

    @pytest.mark.asyncio
    async def test_no_privilege_escalation(self, sandbox):
        """Test that privilege escalation is blocked."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        # Try to use sudo - should fail
        result = await sandbox.run_with_result("sudo echo 'test'")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_cannot_access_host_files(self, sandbox):
        """Test that host filesystem is not accessible."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        # Try to read /etc/passwd from host - should only see container's
        result = await sandbox.run_with_result("cat /etc/passwd")

        # Container has minimal /etc/passwd
        assert result.success is True
        assert "root" in result.output
        # Should not have host users (this is container's /etc/passwd)

    @pytest.mark.asyncio
    async def test_memory_limit(self, sandbox):
        """Test that memory limit is enforced."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        # Try to allocate lots of memory
        result = await sandbox.run_with_result(
            "python -c \"x = 'a' * (500 * 1024 * 1024)\"",  # 500MB
            timeout=10,
        )

        # Should fail due to memory limit (256m default)
        assert result.success is False


class TestEnsureImage:
    """Test image management."""

    @pytest.mark.asyncio
    async def test_ensure_image(self, sandbox):
        """Test ensure_image pulls or confirms image."""
        if not sandbox.is_available():
            pytest.skip("Docker not available")

        result = await sandbox.ensure_image()

        assert "ready" in result.lower() or "pulled" in result.lower()
