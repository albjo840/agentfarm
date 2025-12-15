# CLAUDE.md - AgentFarm

This file provides guidance for Claude Code when working with this repository.

## Project Overview

AgentFarm is a token-efficient multi-agent orchestration system for code tasks. It implements a structured workflow: **PLAN → EXECUTE → VERIFY → REVIEW → SUMMARY**.

### Key Design Principles

1. **Token Efficiency** - Each agent receives minimal, focused context
2. **Provider Abstraction** - Swap LLM providers without code changes
3. **Safe Execution** - All generated code runs in Docker sandbox
4. **MCP Integration** - Exposes tools via Model Context Protocol

## Project Structure

```
agentfarm/
├── policies/
│   └── AGENTS.md              # Repository policy and guidelines
├── src/agentfarm/
│   ├── __init__.py
│   ├── orchestrator.py        # Main workflow coordinator
│   ├── config.py              # Configuration management
│   ├── cli.py                 # Command-line interface
│   ├── mcp_server.py          # MCP server for external integration
│   ├── agents/                # Specialized agents (one per file)
│   │   ├── base.py            # BaseAgent ABC with token optimization
│   │   ├── planner.py         # PlannerAgent - task breakdown
│   │   ├── executor.py        # ExecutorAgent - code changes
│   │   ├── verifier.py        # VerifierAgent - testing/validation
│   │   └── reviewer.py        # ReviewerAgent - code review
│   ├── providers/             # LLM provider implementations
│   │   ├── base.py            # LLMProvider ABC
│   │   └── ollama.py          # Free, local execution (default)
│   ├── tools/                 # Agent tools
│   │   ├── file_tools.py      # File read/write/edit/search
│   │   ├── code_tools.py      # pytest, ruff, typecheck
│   │   ├── git_tools.py       # Git operations
│   │   └── sandbox.py         # Docker sandbox execution
│   └── models/
│       └── schemas.py         # Pydantic models for all data
├── docker/
│   └── Dockerfile.sandbox     # Sandbox container image
├── tests/                     # pytest test suite
└── pyproject.toml             # Project configuration
```

## Development Commands

```bash
# Install for development
pip install -e ".[dev]"

# Install with specific provider
pip install -e ".[ollama]"
pip install -e ".[full]"      # All optional deps

# Run tests
python -m pytest tests/ -v

# Run linter
python -m ruff check src/

# Format code
python -m ruff format src/

# Run CLI
agentfarm workflow "task description"
agentfarm plan "task description"

# Run MCP server
agentfarm mcp
```

## Architecture

### Workflow

```
User Task
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    Orchestrator                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │ PLAN    │→ │ EXECUTE │→ │ VERIFY  │→ │ REVIEW  │    │
│  │ Agent   │  │ Agent   │  │ Agent   │  │ Agent   │    │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │
│       │            │            │            │          │
│       ▼            ▼            ▼            ▼          │
│   TaskPlan    ExecutionResult  VerifyResult  ReviewResult│
└─────────────────────────────────────────────────────────┘
    │
    ▼
WorkflowResult + PR Summary
```

### Token Efficiency Strategy

1. **AgentContext** - Minimal context passed to each agent:
   - `task_summary` - Brief task description
   - `relevant_files` - Only files needed for this step
   - `previous_step_output` - Summary from last agent (not full output)
   - `constraints` - Any limitations

2. **summary_for_next_agent** - Each AgentResult includes a concise summary for handoff

3. **Tool filtering** - Each agent only has access to its specific tools

### Provider System

```python
# Default: Ollama (free, local)
from agentfarm.providers.ollama import OllamaProvider
provider = OllamaProvider(model="llama3.2")

# Future: Other providers
# from agentfarm.providers.claude import ClaudeProvider
# from agentfarm.providers.azure import AzureOpenAIProvider
```

Environment variables:
- `AGENTFARM_PROVIDER` - ollama, groq, claude, azure_openai
- `AGENTFARM_MODEL` - Model name
- `AGENTFARM_API_KEY` - API key (if needed)
- `OLLAMA_HOST` - Ollama server URL

## Key Files to Understand

| File | Purpose |
|------|---------|
| `orchestrator.py` | Main entry point, coordinates full workflow |
| `agents/base.py` | BaseAgent class with token optimization logic |
| `providers/base.py` | LLMProvider ABC for provider abstraction |
| `models/schemas.py` | All Pydantic models (TaskPlan, ExecutionResult, etc.) |
| `tools/sandbox.py` | Docker sandbox for safe code execution |
| `mcp_server.py` | MCP server exposing tools externally |

## Code Patterns

### Adding a New Agent

```python
# src/agentfarm/agents/my_agent.py
from agentfarm.agents.base import BaseAgent, AgentContext, AgentResult

class MyAgent(BaseAgent):
    name = "MyAgent"

    @property
    def system_prompt(self) -> str:
        return "Your minimal, focused system prompt"

    def get_tools(self) -> list[ToolDefinition]:
        return self._tools  # Only tools this agent needs

    async def process_response(self, response, tool_outputs) -> AgentResult:
        # Parse response into structured result
        return AgentResult(
            success=True,
            output=response.content,
            summary_for_next_agent="Concise summary for next agent",
        )
```

### Adding a New Provider

```python
# src/agentfarm/providers/my_provider.py
from agentfarm.providers.base import LLMProvider, CompletionResponse

class MyProvider(LLMProvider):
    async def complete(self, messages, tools=None, **kwargs) -> CompletionResponse:
        # Call your LLM API
        return CompletionResponse(content="...", input_tokens=X, output_tokens=Y)

    async def stream(self, messages, **kwargs):
        # Yield tokens
        yield "token"
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_schemas.py -v

# Run with coverage (requires pytest-cov)
python -m pytest tests/ --cov=agentfarm
```

Test files:
- `test_schemas.py` - Pydantic model tests
- `test_providers.py` - Provider abstraction tests
- `test_agents.py` - Agent context/result tests
- `test_tools.py` - File tools tests (requires aiofiles)

## Policy Compliance

All changes must follow `policies/AGENTS.md`:
- Use the PLAN→EXECUTE→VERIFY→REVIEW workflow
- Type hints required on all functions
- Async/await for I/O operations
- Pydantic for data models
- Maximum 200 lines per logical change

## Common Tasks

### Run a workflow programmatically

```python
import asyncio
from agentfarm import Orchestrator
from agentfarm.providers.ollama import OllamaProvider

async def main():
    provider = OllamaProvider(model="llama3.2")
    orchestrator = Orchestrator(provider, working_dir="./my_project")

    result = await orchestrator.run_workflow(
        task="Add unit tests for utils.py",
        context_files=["src/utils.py"],
    )

    print(result.pr_summary)

asyncio.run(main())
```

### Use as MCP server

Add to Claude Desktop config:
```json
{
  "mcpServers": {
    "agentfarm": {
      "command": "agentfarm",
      "args": ["mcp"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

## Dependencies

Core (always installed):
- `pydantic` - Data validation
- `httpx` - Async HTTP client
- `aiofiles` - Async file operations

Optional:
- `mcp` - MCP server support
- `docker` - Sandbox execution
- `gitpython` - Git operations
- `anthropic` - Claude provider
- `ollama` - Ollama provider

Dev:
- `pytest`, `pytest-asyncio` - Testing
- `ruff` - Linting/formatting
