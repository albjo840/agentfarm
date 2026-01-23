from __future__ import annotations

"""MCP server for AgentFarm - exposes multi-agent workflow as tools and resources."""

import asyncio
import json
import mimetypes
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    BlobResourceContents,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)

from agentfarm.agents.base import AgentContext
from agentfarm.mcp import get_eval_tool_handler, get_prompt_tool_handler, get_testing_tool_handler
from agentfarm.models.schemas import TaskPlan, WorkflowResult
from agentfarm.orchestrator import Orchestrator
from agentfarm.providers.ollama import OllamaProvider
from agentfarm.tools.code_tools import CodeTools
from agentfarm.tools.file_tools import FileTools
from agentfarm.tools.git_tools import GitTools
from agentfarm.tools.sandbox import SandboxRunner

# Global orchestrator instance
_orchestrator: Orchestrator | None = None
_working_dir: str = "."

# File patterns to expose as resources
RESOURCE_PATTERNS = [
    "*.py",
    "*.js",
    "*.ts",
    "*.html",
    "*.css",
    "*.json",
    "*.yaml",
    "*.yml",
    "*.md",
    "*.txt",
    "*.toml",
    "*.cfg",
    "*.ini",
]

# Directories to exclude
EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "venv",
    ".eggs",
    "*.egg-info",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
}

# Handler instances
_eval_handler = None
_prompt_handler = None
_testing_handler = None


def get_eval_handler():
    """Get or create the eval tool handler instance."""
    global _eval_handler
    if _eval_handler is None:
        EvalToolHandler = get_eval_tool_handler()
        _eval_handler = EvalToolHandler(_working_dir)
    return _eval_handler


def get_prompt_handler():
    """Get or create the prompt tool handler instance."""
    global _prompt_handler
    if _prompt_handler is None:
        PromptToolHandler = get_prompt_tool_handler()
        _prompt_handler = PromptToolHandler(_working_dir)
    return _prompt_handler


def get_testing_handler():
    """Get or create the testing tool handler instance."""
    global _testing_handler
    if _testing_handler is None:
        TestingToolHandler = get_testing_tool_handler()
        _testing_handler = TestingToolHandler(_working_dir)
    return _testing_handler


def get_orchestrator() -> Orchestrator:
    """Get or create the orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        provider = OllamaProvider(model="llama3.2")
        _orchestrator = Orchestrator(provider, working_dir=_working_dir)

        # Inject tools
        file_tools = FileTools(_working_dir)
        code_tools = CodeTools(_working_dir)
        git_tools = GitTools(_working_dir)
        sandbox = SandboxRunner(_working_dir)

        _orchestrator.inject_tools(file_tools, code_tools, git_tools, sandbox)

    return _orchestrator


# Create MCP server
server = Server("agentfarm")


# =============================================================================
# RESOURCES - Expose project files to Claude Desktop
# =============================================================================


def _get_project_files() -> list[Path]:
    """Get all project files matching resource patterns."""
    working_path = Path(_working_dir).resolve()
    files = []

    for pattern in RESOURCE_PATTERNS:
        for file_path in working_path.rglob(pattern):
            # Skip excluded directories
            parts = file_path.relative_to(working_path).parts
            if any(excluded in parts for excluded in EXCLUDE_DIRS):
                continue

            # Skip if file is too large (>1MB)
            if file_path.stat().st_size > 1_000_000:
                continue

            files.append(file_path)

    return sorted(files)


def _file_to_uri(file_path: Path) -> str:
    """Convert file path to resource URI."""
    working_path = Path(_working_dir).resolve()
    relative = file_path.relative_to(working_path)
    return f"file:///{relative.as_posix()}"


def _uri_to_file(uri: str) -> Path:
    """Convert resource URI to file path."""
    # Remove file:/// prefix
    relative = uri.replace("file:///", "")
    return Path(_working_dir).resolve() / relative


@server.list_resources()
async def list_resources() -> list[Resource]:
    """List all project files as MCP resources."""
    resources = []

    for file_path in _get_project_files():
        uri = _file_to_uri(file_path)
        mime_type, _ = mimetypes.guess_type(str(file_path))

        resources.append(
            Resource(
                uri=uri,
                name=file_path.name,
                description=f"Project file: {file_path.relative_to(Path(_working_dir).resolve())}",
                mimeType=mime_type or "text/plain",
            )
        )

    return resources


@server.read_resource()
async def read_resource(uri: str) -> TextResourceContents | BlobResourceContents:
    """Read a project file by URI."""
    file_path = _uri_to_file(uri)

    if not file_path.exists():
        raise FileNotFoundError(f"Resource not found: {uri}")

    # Security check: ensure file is within working directory
    working_path = Path(_working_dir).resolve()
    if not file_path.resolve().is_relative_to(working_path):
        raise PermissionError(f"Access denied: {uri}")

    mime_type, _ = mimetypes.guess_type(str(file_path))

    # Text files
    if mime_type is None or mime_type.startswith("text/") or file_path.suffix in [
        ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".md", ".txt", ".toml", ".cfg", ".ini"
    ]:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return TextResourceContents(
            uri=uri,
            mimeType=mime_type or "text/plain",
            text=content,
        )

    # Binary files
    content = file_path.read_bytes()
    import base64
    return BlobResourceContents(
        uri=uri,
        mimeType=mime_type or "application/octet-stream",
        blob=base64.b64encode(content).decode("ascii"),
    )


# =============================================================================
# TOOLS - Agent workflow operations
# =============================================================================


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="plan_task",
            description="Plan a task and break it into executable steps",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Description of the task to plan",
                    },
                    "context_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Files relevant to the task",
                    },
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="execute_step",
            description="Execute a single step from a plan",
            inputSchema={
                "type": "object",
                "properties": {
                    "step_description": {
                        "type": "string",
                        "description": "Description of the step to execute",
                    },
                    "step_id": {
                        "type": "integer",
                        "description": "Step ID for tracking",
                    },
                    "context": {
                        "type": "string",
                        "description": "Additional context for execution",
                    },
                },
                "required": ["step_description", "step_id"],
            },
        ),
        Tool(
            name="verify_changes",
            description="Run tests and validate code changes",
            inputSchema={
                "type": "object",
                "properties": {
                    "changed_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of changed files to verify",
                    },
                },
                "required": ["changed_files"],
            },
        ),
        Tool(
            name="review_code",
            description="Review code changes for quality and correctness",
            inputSchema={
                "type": "object",
                "properties": {
                    "changed_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Files to review",
                    },
                    "diff": {
                        "type": "string",
                        "description": "Diff of changes (optional)",
                    },
                },
                "required": ["changed_files"],
            },
        ),
        Tool(
            name="run_workflow",
            description="Run complete PLAN→EXECUTE→VERIFY→REVIEW workflow",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task to accomplish",
                    },
                    "context_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Relevant files",
                    },
                    "constraints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Constraints to follow",
                    },
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="get_token_usage",
            description="Get total tokens used in current session",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="list_project_files",
            description="List all files in the project directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter files (e.g., '*.py', 'src/**/*.ts')",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Subdirectory to list (relative to project root)",
                    },
                },
            },
        ),
        Tool(
            name="read_file",
            description="Read the contents of a file",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to file (relative to project root)",
                    },
                },
                "required": ["path"],
            },
        ),
        # Evaluation Tools
        Tool(
            name="run_eval",
            description="Run evaluation suite with optional category filter",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category to run: codegen, bugfix, refactor, multistep",
                        "enum": ["codegen", "bugfix", "refactor", "multistep"],
                    },
                    "quick": {
                        "type": "boolean",
                        "description": "Run quick mode (fewer tests)",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="list_evals",
            description="List all available evaluation tests",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="run_single_eval",
            description="Run a specific evaluation test by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_id": {
                        "type": "string",
                        "description": "Test ID (e.g., 'codegen-001')",
                    },
                    "verbose": {
                        "type": "boolean",
                        "description": "Show verbose output",
                        "default": False,
                    },
                },
                "required": ["test_id"],
            },
        ),
        Tool(
            name="get_eval_results",
            description="Get recent evaluation results",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 10,
                    },
                },
            },
        ),
        # Prompt Introspection Tools
        Tool(
            name="get_prompt",
            description="Get the system prompt for an agent",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "Agent name: planner, executor, verifier, reviewer, ux_designer, orchestrator",
                    },
                },
                "required": ["agent"],
            },
        ),
        Tool(
            name="list_prompts",
            description="List all agent prompts with metadata",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="test_prompt",
            description="Test a prompt with sample input",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "Agent name to test",
                    },
                    "test_input": {
                        "type": "string",
                        "description": "Sample input to test with",
                    },
                    "custom_suffix": {
                        "type": "string",
                        "description": "Optional custom prompt suffix",
                    },
                },
                "required": ["agent", "test_input"],
            },
        ),
        # Workflow Testing Tools
        Tool(
            name="test_agent",
            description="Test a single agent with specific input",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "Agent to test: planner, executor, verifier, reviewer",
                    },
                    "task": {
                        "type": "string",
                        "description": "Task description for the agent",
                    },
                    "context_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Context files for the task",
                    },
                },
                "required": ["agent", "task"],
            },
        ),
        Tool(
            name="run_quick_test",
            description="Run quick sanity tests",
            inputSchema={
                "type": "object",
                "properties": {
                    "component": {
                        "type": "string",
                        "description": "Component to test: imports, agents, tools, memory",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    orchestrator = get_orchestrator()

    try:
        if name == "plan_task":
            result = await _handle_plan_task(orchestrator, arguments)
        elif name == "execute_step":
            result = await _handle_execute_step(orchestrator, arguments)
        elif name == "verify_changes":
            result = await _handle_verify_changes(orchestrator, arguments)
        elif name == "review_code":
            result = await _handle_review_code(orchestrator, arguments)
        elif name == "run_workflow":
            result = await _handle_run_workflow(orchestrator, arguments)
        elif name == "get_token_usage":
            result = _handle_get_token_usage(orchestrator)
        elif name == "list_project_files":
            result = _handle_list_project_files(arguments)
        elif name == "read_file":
            result = _handle_read_file(arguments)
        # Evaluation Tools
        elif name == "run_eval":
            result = await get_eval_handler().run_eval(
                arguments.get("category"), arguments.get("quick", False)
            )
        elif name == "list_evals":
            result = get_eval_handler().list_evals()
        elif name == "run_single_eval":
            result = await get_eval_handler().run_single_eval(
                arguments["test_id"], arguments.get("verbose", False)
            )
        elif name == "get_eval_results":
            result = get_eval_handler().get_eval_results(arguments.get("limit", 10))
        # Prompt Introspection Tools
        elif name == "get_prompt":
            result = get_prompt_handler().get_prompt(arguments["agent"])
        elif name == "list_prompts":
            result = get_prompt_handler().list_prompts()
        elif name == "test_prompt":
            result = await get_prompt_handler().test_prompt(
                arguments["agent"],
                arguments["test_input"],
                arguments.get("custom_suffix"),
            )
        # Workflow Testing Tools
        elif name == "test_agent":
            result = await get_testing_handler().test_agent(
                arguments["agent"],
                arguments["task"],
                arguments.get("context_files"),
            )
        elif name == "run_quick_test":
            result = get_testing_handler().run_quick_test(arguments.get("component"))
        else:
            result = f"Unknown tool: {name}"

        return [TextContent(type="text", text=str(result))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _handle_plan_task(
    orchestrator: Orchestrator, args: dict[str, Any]
) -> str:
    """Handle plan_task tool call."""
    task = args["task"]
    context_files = args.get("context_files", [])

    context = AgentContext(
        task_summary=task,
        relevant_files=context_files,
    )

    plan = await orchestrator.planner.create_plan(context, task)
    if plan:
        return json.dumps(plan.model_dump(), indent=2)
    return "Failed to create plan"


async def _handle_execute_step(
    orchestrator: Orchestrator, args: dict[str, Any]
) -> str:
    """Handle execute_step tool call."""
    step_description = args["step_description"]
    step_id = args["step_id"]
    context_str = args.get("context", "")

    context = AgentContext(
        task_summary=step_description,
        previous_step_output=context_str if context_str else None,
    )

    result = await orchestrator.executor.execute_step(context, step_description, step_id)
    return json.dumps(result.model_dump(), indent=2)


async def _handle_verify_changes(
    orchestrator: Orchestrator, args: dict[str, Any]
) -> str:
    """Handle verify_changes tool call."""
    changed_files = args["changed_files"]

    context = AgentContext(
        task_summary="Verify code changes",
        relevant_files=changed_files,
    )

    result = await orchestrator.verifier.verify_changes(context, changed_files)
    return json.dumps(result.model_dump(), indent=2)


async def _handle_review_code(
    orchestrator: Orchestrator, args: dict[str, Any]
) -> str:
    """Handle review_code tool call."""
    changed_files = args["changed_files"]
    diff = args.get("diff")

    context = AgentContext(
        task_summary="Review code changes",
        relevant_files=changed_files,
    )

    result = await orchestrator.reviewer.review_changes(context, changed_files, diff)
    return json.dumps(result.model_dump(), indent=2)


async def _handle_run_workflow(
    orchestrator: Orchestrator, args: dict[str, Any]
) -> str:
    """Handle run_workflow tool call."""
    task = args["task"]
    context_files = args.get("context_files")
    constraints = args.get("constraints")

    result = await orchestrator.run_workflow(task, context_files, constraints)
    return json.dumps(result.model_dump(), indent=2)


def _handle_get_token_usage(orchestrator: Orchestrator) -> str:
    """Handle get_token_usage tool call."""
    tokens = orchestrator.provider.total_tokens_used
    return json.dumps({"total_tokens_used": tokens})


def _handle_list_project_files(args: dict[str, Any]) -> str:
    """Handle list_project_files tool call."""
    pattern = args.get("pattern", "*")
    directory = args.get("directory", "")

    working_path = Path(_working_dir).resolve()
    search_path = working_path / directory if directory else working_path

    if not search_path.exists():
        return json.dumps({"error": f"Directory not found: {directory}"})

    # Security check
    if not search_path.resolve().is_relative_to(working_path):
        return json.dumps({"error": "Access denied"})

    files = []
    for file_path in search_path.rglob(pattern):
        # Skip excluded directories
        try:
            parts = file_path.relative_to(working_path).parts
            if any(excluded in parts for excluded in EXCLUDE_DIRS):
                continue
        except ValueError:
            continue

        if file_path.is_file():
            rel_path = file_path.relative_to(working_path)
            files.append({
                "path": str(rel_path),
                "size": file_path.stat().st_size,
                "type": file_path.suffix or "unknown",
            })

    # Sort by path and limit to 500 files
    files = sorted(files, key=lambda f: f["path"])[:500]

    return json.dumps({
        "directory": directory or ".",
        "pattern": pattern,
        "count": len(files),
        "files": files,
    }, indent=2)


def _handle_read_file(args: dict[str, Any]) -> str:
    """Handle read_file tool call."""
    path = args.get("path", "")

    if not path:
        return json.dumps({"error": "Path is required"})

    working_path = Path(_working_dir).resolve()
    file_path = working_path / path

    # Security check
    if not file_path.resolve().is_relative_to(working_path):
        return json.dumps({"error": "Access denied"})

    if not file_path.exists():
        return json.dumps({"error": f"File not found: {path}"})

    if not file_path.is_file():
        return json.dumps({"error": f"Not a file: {path}"})

    # Size limit (1MB)
    if file_path.stat().st_size > 1_000_000:
        return json.dumps({"error": "File too large (>1MB)"})

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return json.dumps({
            "path": path,
            "size": len(content),
            "content": content,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


async def run_server() -> None:
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """Entry point for MCP server."""
    import sys

    global _working_dir

    # Accept working directory as argument
    if len(sys.argv) > 1:
        _working_dir = sys.argv[1]

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
