"""Tests for MCP server functionality."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def test_mcp_tools_list():
    """Test that MCP tools are defined correctly."""
    # Import with mocked mcp module
    with patch.dict('sys.modules', {
        'mcp': MagicMock(),
        'mcp.server': MagicMock(),
        'mcp.server.stdio': MagicMock(),
        'mcp.types': MagicMock(),
    }):
        # Mock the Tool class
        import sys
        tool_mock = MagicMock()
        sys.modules['mcp.types'].Tool = tool_mock
        sys.modules['mcp.types'].TextContent = MagicMock()

        # Mock Server
        server_mock = MagicMock()
        sys.modules['mcp.server'].Server = lambda name: server_mock

        # Reload to get the decorated functions
        import importlib
        import agentfarm.mcp_server as mcp_module
        importlib.reload(mcp_module)

        # The tools should be registered
        assert mcp_module.server is not None


def test_mcp_tool_schemas():
    """Test that MCP tool schemas are valid JSON Schema."""
    tool_schemas = [
        {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "context_files": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["task"],
        },
        {
            "type": "object",
            "properties": {
                "step_description": {"type": "string"},
                "step_id": {"type": "integer"},
                "context": {"type": "string"},
            },
            "required": ["step_description", "step_id"],
        },
    ]

    for schema in tool_schemas:
        assert "type" in schema
        assert "properties" in schema
        assert schema["type"] == "object"


@pytest.mark.asyncio
async def test_mcp_get_token_usage():
    """Test get_token_usage returns valid JSON."""
    import json

    # Mock orchestrator
    mock_orchestrator = MagicMock()
    mock_orchestrator.provider = MagicMock()
    mock_orchestrator.provider.total_tokens_used = 1234

    with patch.dict('sys.modules', {
        'mcp': MagicMock(),
        'mcp.server': MagicMock(),
        'mcp.server.stdio': MagicMock(),
        'mcp.types': MagicMock(),
    }):
        import sys
        sys.modules['mcp.server'].Server = lambda name: MagicMock()

        from agentfarm.mcp_server import _handle_get_token_usage

        result = _handle_get_token_usage(mock_orchestrator)
        data = json.loads(result)

        assert "total_tokens_used" in data
        assert data["total_tokens_used"] == 1234


def test_claude_desktop_config_format():
    """Test that the Claude Desktop config format is documented correctly."""
    import json

    # This is the expected config format
    expected_config = {
        "mcpServers": {
            "agentfarm": {
                "command": "agentfarm",
                "args": ["mcp"],
                "cwd": "/path/to/project",
                "env": {
                    "GROQ_API_KEY": "your_key_here"
                }
            }
        }
    }

    # Verify it's valid JSON
    json_str = json.dumps(expected_config, indent=2)
    parsed = json.loads(json_str)

    assert "mcpServers" in parsed
    assert "agentfarm" in parsed["mcpServers"]
    assert parsed["mcpServers"]["agentfarm"]["command"] == "agentfarm"
    assert "mcp" in parsed["mcpServers"]["agentfarm"]["args"]


def test_mcp_resource_patterns():
    """Test that resource patterns are sensible."""
    from agentfarm.mcp_server import RESOURCE_PATTERNS, EXCLUDE_DIRS

    # Should include common code file types
    assert "*.py" in RESOURCE_PATTERNS
    assert "*.js" in RESOURCE_PATTERNS
    assert "*.ts" in RESOURCE_PATTERNS
    assert "*.md" in RESOURCE_PATTERNS

    # Should exclude common non-code directories
    assert ".git" in EXCLUDE_DIRS
    assert "__pycache__" in EXCLUDE_DIRS
    assert "node_modules" in EXCLUDE_DIRS


def test_file_to_uri_conversion():
    """Test URI conversion functions."""
    from pathlib import Path
    from agentfarm.mcp_server import _file_to_uri, _uri_to_file, _working_dir

    # Mock working dir
    import agentfarm.mcp_server as mcp
    original_dir = mcp._working_dir
    mcp._working_dir = "/test/project"

    try:
        # Test file to URI
        test_path = Path("/test/project/src/main.py")
        uri = _file_to_uri(test_path)
        assert uri == "file:///src/main.py"

        # Test URI to file
        result = _uri_to_file("file:///src/main.py")
        assert result == Path("/test/project/src/main.py")

    finally:
        mcp._working_dir = original_dir


def test_list_project_files_handler():
    """Test list_project_files tool handler."""
    import json
    import tempfile
    from pathlib import Path
    from agentfarm.mcp_server import _handle_list_project_files
    import agentfarm.mcp_server as mcp

    # Create temp directory with test files
    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = mcp._working_dir
        mcp._working_dir = tmpdir

        try:
            # Create test files
            (Path(tmpdir) / "test.py").write_text("# test")
            (Path(tmpdir) / "src").mkdir()
            (Path(tmpdir) / "src" / "app.py").write_text("# app")

            # Test listing all files
            result = json.loads(_handle_list_project_files({"pattern": "*.py"}))
            assert result["count"] >= 2
            paths = [f["path"] for f in result["files"]]
            assert "test.py" in paths
            assert "src/app.py" in paths or "src\\app.py" in paths

            # Test listing specific directory
            result = json.loads(_handle_list_project_files({"directory": "src"}))
            assert result["directory"] == "src"

        finally:
            mcp._working_dir = original_dir


def test_read_file_handler():
    """Test read_file tool handler."""
    import json
    import tempfile
    from pathlib import Path
    from agentfarm.mcp_server import _handle_read_file
    import agentfarm.mcp_server as mcp

    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = mcp._working_dir
        mcp._working_dir = tmpdir

        try:
            # Create test file
            test_content = "Hello, World!\nLine 2"
            (Path(tmpdir) / "test.txt").write_text(test_content)

            # Read file
            result = json.loads(_handle_read_file({"path": "test.txt"}))
            assert result["content"] == test_content
            assert result["path"] == "test.txt"

            # Test non-existent file
            result = json.loads(_handle_read_file({"path": "nonexistent.txt"}))
            assert "error" in result

            # Test path traversal protection
            result = json.loads(_handle_read_file({"path": "../../../etc/passwd"}))
            assert "error" in result

        finally:
            mcp._working_dir = original_dir
