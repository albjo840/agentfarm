from __future__ import annotations

"""MCP server for AgentFarm - exposes multi-agent workflow as tools."""

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from agentfarm.agents.base import AgentContext
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
