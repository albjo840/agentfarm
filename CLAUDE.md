# CLAUDE.md - AgentFarm

This file provides guidance for Claude Code when working with this repository.

## Project Overview

AgentFarm is a token-efficient multi-agent orchestration system for code tasks. It implements a structured workflow: **PLAN → EXECUTE → VERIFY → REVIEW → SUMMARY**.

### Key Design Principles

1. **Token Efficiency** - Each agent receives minimal, focused context
2. **Provider Abstraction** - Swap LLM providers without code changes
3. **Safe Execution** - All generated code runs in Docker sandbox
4. **MCP Integration** - Exposes tools via Model Context Protocol
5. **Free-First** - Groq free tier as default, no cost to get started

## Quick Start

```bash
# Set up API key (get free key at https://console.groq.com/keys)
export GROQ_API_KEY=your_key_here

# Install
pip install -e ".[dev]"

# Run a plan
agentfarm plan "Add a hello world function"

# Run full workflow
agentfarm workflow "Add unit tests for utils.py"
```

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
│   │   ├── groq.py            # Groq API (default, free tier)
│   │   └── ollama.py          # Ollama (local, free)
│   ├── tools/                 # Agent tools
│   │   ├── file_tools.py      # File read/write/edit/search
│   │   ├── code_tools.py      # pytest, ruff, typecheck
│   │   ├── git_tools.py       # Git operations
│   │   └── sandbox.py         # Docker sandbox execution
│   └── models/
│       └── schemas.py         # Pydantic models for all data
├── docker/
│   └── Dockerfile.sandbox     # Sandbox container image
├── tests/                     # pytest test suite (27 tests)
├── .env                       # API keys (not in git)
└── pyproject.toml             # Project configuration
```

## Development Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Run linter
python -m ruff check src/

# Format code
python -m ruff format src/

# Run CLI (requires GROQ_API_KEY)
agentfarm plan "task description"
agentfarm workflow "task description"

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
# Default: Groq (free tier, fast)
from agentfarm.providers.groq import GroqProvider
provider = GroqProvider(model="llama-3.3-70b-versatile")

# Alternative: Ollama (local, free)
from agentfarm.providers.ollama import OllamaProvider
provider = OllamaProvider(model="llama3.2")

# Future: Claude, Azure AI Foundry
# from agentfarm.providers.claude import ClaudeProvider
# from agentfarm.providers.azure import AzureOpenAIProvider
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | (required) | Groq API key from console.groq.com |
| `AGENTFARM_PROVIDER` | `groq` | Provider: groq, ollama, claude, azure_openai |
| `AGENTFARM_MODEL` | `llama-3.3-70b-versatile` | Model name |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |

## Key Files to Understand

| File | Purpose |
|------|---------|
| `orchestrator.py` | Main entry point, coordinates full workflow |
| `agents/base.py` | BaseAgent class with token optimization logic |
| `providers/base.py` | LLMProvider ABC for provider abstraction |
| `providers/groq.py` | Default provider (Groq free tier) |
| `models/schemas.py` | All Pydantic models (TaskPlan, ExecutionResult, etc.) |
| `tools/sandbox.py` | Docker sandbox for safe code execution |
| `mcp_server.py` | MCP server exposing tools externally |
| `config.py` | Configuration with env var support |

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
from agentfarm.providers.groq import GroqProvider

async def main():
    provider = GroqProvider(model="llama-3.3-70b-versatile")
    orchestrator = Orchestrator(provider, working_dir="./my_project")

    result = await orchestrator.run_workflow(
        task="Add unit tests for utils.py",
        context_files=["src/utils.py"],
    )

    print(result.pr_summary)
    print(f"Tokens used: {result.total_tokens_used}")

asyncio.run(main())
```

### Use as MCP server

Add to Claude Desktop config (`~/.config/claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "agentfarm": {
      "command": "agentfarm",
      "args": ["mcp"],
      "cwd": "/path/to/your/project",
      "env": {
        "GROQ_API_KEY": "your_key_here"
      }
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
- `groq` - Groq provider (SDK, optional - httpx used by default)

Dev:
- `pytest`, `pytest-asyncio` - Testing
- `ruff` - Linting/formatting

## Roadmap / TODO

### Priority 1: Core Functionality
- [ ] Integration tests with Groq API
- [ ] Retry logic for rate limits (429 errors)
- [ ] Connect real FileTools to agents

### Priority 2: More Providers
- [ ] ClaudeProvider (`providers/claude.py`)
- [ ] AzureOpenAIProvider (`providers/azure.py`)
- [ ] Provider auto-detection from available API keys

### Priority 3: MCP & Integration
- [ ] Test MCP server with Claude Desktop
- [ ] Add MCP resources for project files
- [ ] VS Code extension integration

### Priority 4: Security & Sandbox
- [ ] Build and test Docker sandbox image
- [ ] Timeout handling for sandbox execution
- [ ] Resource limits enforcement

### Priority 5: Improvements
- [ ] Streaming output for real-time feedback
- [ ] Token usage dashboard per agent
- [ ] Response caching for identical requests
- [ ] Structured logging for debugging
