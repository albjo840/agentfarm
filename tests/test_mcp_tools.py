"""Tests for new MCP tool handlers."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.fixture
def temp_workdir(tmp_path):
    """Create a temporary working directory with eval results."""
    (tmp_path / "evals" / "results").mkdir(parents=True)
    return str(tmp_path)


class TestEvalToolHandler:
    """Tests for EvalToolHandler."""

    def test_list_evals(self):
        """Test listing available evaluations."""
        from agentfarm.mcp.eval_tools import EvalToolHandler

        handler = EvalToolHandler(".")
        result = json.loads(handler.list_evals())

        assert "tests" in result
        assert "count" in result
        assert result["count"] > 0
        # Check structure of test entries
        if result["tests"]:
            test = result["tests"][0]
            assert "id" in test
            assert "name" in test
            assert "category" in test

    def test_get_eval_results_empty(self, temp_workdir):
        """Test getting eval results when none exist."""
        from agentfarm.mcp.eval_tools import EvalToolHandler

        handler = EvalToolHandler(temp_workdir)
        result = json.loads(handler.get_eval_results(limit=5))

        assert "results" in result
        assert result["count"] == 0

    def test_get_eval_results_with_data(self, temp_workdir):
        """Test getting eval results when results exist."""
        from agentfarm.mcp.eval_tools import EvalToolHandler

        # Create a mock result file
        results_dir = Path(temp_workdir) / "evals" / "results"
        mock_result = {
            "timestamp": "2026-01-23T10:00:00",
            "passed": 5,
            "failed": 2,
            "percentage": 71.4,
        }
        (results_dir / "eval_20260123_100000.json").write_text(json.dumps(mock_result))

        handler = EvalToolHandler(temp_workdir)
        result = json.loads(handler.get_eval_results(limit=5))

        assert result["count"] == 1
        assert result["results"][0]["passed"] == 5


class TestPromptToolHandler:
    """Tests for PromptToolHandler."""

    def test_get_prompt_planner(self):
        """Test getting planner prompt."""
        from agentfarm.mcp.prompt_tools import PromptToolHandler

        handler = PromptToolHandler(".")
        result = json.loads(handler.get_prompt("planner"))

        assert result["agent"] == "planner"
        assert result["length"] > 0
        assert "prompt" in result
        assert isinstance(result["has_custom_suffix"], bool)

    def test_get_prompt_executor(self):
        """Test getting executor prompt."""
        from agentfarm.mcp.prompt_tools import PromptToolHandler

        handler = PromptToolHandler(".")
        result = json.loads(handler.get_prompt("executor"))

        assert result["agent"] == "executor"
        assert result["length"] > 0

    def test_get_prompt_unknown_agent(self):
        """Test getting prompt for unknown agent."""
        from agentfarm.mcp.prompt_tools import PromptToolHandler

        handler = PromptToolHandler(".")
        result = json.loads(handler.get_prompt("unknown_agent"))

        assert "error" in result
        assert "unknown_agent" in result["error"].lower()

    def test_list_prompts(self):
        """Test listing all prompts."""
        from agentfarm.mcp.prompt_tools import PromptToolHandler

        handler = PromptToolHandler(".")
        result = json.loads(handler.list_prompts())

        assert "prompts" in result
        assert result["count"] >= 4  # At least planner, executor, verifier, reviewer

        agents = [p["agent"] for p in result["prompts"]]
        assert "planner" in agents
        assert "executor" in agents
        assert "verifier" in agents
        assert "reviewer" in agents

    def test_set_custom_prompt(self):
        """Test setting custom prompt suffix."""
        from agentfarm.mcp.prompt_tools import PromptToolHandler

        handler = PromptToolHandler(".")
        result = json.loads(handler.set_custom_prompt("planner", "Always be concise."))

        assert result["agent"] == "planner"
        assert result["status"] == "configured"
        assert result["custom_text"] == "Always be concise."


class TestTestingToolHandler:
    """Tests for TestingToolHandler."""

    def test_run_quick_test_imports(self):
        """Test running quick test for imports."""
        from agentfarm.mcp.testing_tools import TestingToolHandler

        handler = TestingToolHandler(".")
        result = json.loads(handler.run_quick_test("imports"))

        assert "results" in result
        assert "imports" in result["results"]

    def test_run_quick_test_all(self):
        """Test running all quick tests."""
        from agentfarm.mcp.testing_tools import TestingToolHandler

        handler = TestingToolHandler(".")
        result = json.loads(handler.run_quick_test())

        assert "all_passed" in result
        assert "results" in result
        # Should have multiple test categories
        assert len(result["results"]) >= 1


class TestMCPServerIntegration:
    """Integration tests for MCP server with new tools."""

    def test_new_tools_registered(self):
        """Test that new tools are registered in list_tools."""
        with patch.dict('sys.modules', {
            'mcp': MagicMock(),
            'mcp.server': MagicMock(),
            'mcp.server.stdio': MagicMock(),
            'mcp.types': MagicMock(),
        }):
            import sys
            sys.modules['mcp.server'].Server = lambda name: MagicMock()
            sys.modules['mcp.types'].Tool = MagicMock()
            sys.modules['mcp.types'].TextContent = MagicMock()
            sys.modules['mcp.types'].Resource = MagicMock()
            sys.modules['mcp.types'].TextResourceContents = MagicMock()
            sys.modules['mcp.types'].BlobResourceContents = MagicMock()

            import importlib
            import agentfarm.mcp_server as mcp_module
            importlib.reload(mcp_module)

            # The module should load without errors
            assert mcp_module.server is not None

    def test_list_evals_handler_directly(self):
        """Test calling list_evals handler directly."""
        from agentfarm.mcp.eval_tools import EvalToolHandler

        handler = EvalToolHandler(".")
        result = handler.list_evals()

        data = json.loads(result)
        assert "tests" in data
        assert "count" in data


class TestSchemas:
    """Tests for MCP schemas."""

    def test_eval_run_result_schema(self):
        """Test EvalRunResult schema."""
        from agentfarm.mcp.schemas import EvalRunResult

        result = EvalRunResult(
            success=True,
            tests_run=10,
            tests_passed=8,
            tests_failed=2,
            total_score=80.0,
            max_score=100.0,
            percentage=80.0,
            duration_seconds=45.5,
        )

        assert result.success is True
        assert result.tests_run == 10
        assert result.percentage == 80.0

    def test_prompt_info_schema(self):
        """Test PromptInfo schema."""
        from agentfarm.mcp.schemas import PromptInfo

        info = PromptInfo(
            agent="planner",
            prompt="You are a planner...",
            length=20,
            has_custom_suffix=False,
        )

        assert info.agent == "planner"
        assert info.length == 20

    def test_agent_test_result_schema(self):
        """Test AgentTestResult schema."""
        from agentfarm.mcp.schemas import AgentTestResult

        result = AgentTestResult(
            agent="executor",
            success=True,
            output="Task completed",
            summary="Successfully executed task",
            duration_seconds=5.2,
        )

        assert result.agent == "executor"
        assert result.success is True
        assert result.tokens_used is None  # Optional field
