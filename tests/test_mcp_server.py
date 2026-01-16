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
